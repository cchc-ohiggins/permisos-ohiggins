// Recorre el Portal de Transparencia (CPLT) para las 33 comunas y arma data/manifiesto.json:
// una fila por documento publicado (art. 116 bis C LGUC) con comuna, mes, N° de resolución y enlace al PDF.
// Uso:  node scripts/portal.js            (todas las comunas)
//       node scripts/portal.js rancagua rengo   (solo algunas)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..');
const codigos = JSON.parse(fs.readFileSync(path.join(RAIZ, 'data/portal_codigos.json'), 'utf8'));
const paginaSrc = fs.readFileSync(path.join(__dirname, 'portal_page.js'), 'utf8');
const MES = { enero: 1, febrero: 2, marzo: 3, abril: 4, mayo: 5, junio: 6, julio: 7, agosto: 8, septiembre: 9, setiembre: 9, octubre: 10, noviembre: 11, diciembre: 12 };
const MES_TXT = ['', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'];
const DESDE = '2025-05'; // la Ley 21.718 rige desde mayo de 2025

const ym = (y, m) => `${y}-${String(m).padStart(2, '0')}`;

function normalizar(slug, res) {
  const filas = [];
  for (const r of res.rows || []) {
    const td = r.td || [];
    const anio = (td[0] || r.y || '').match(/20\d\d/);
    const mes = MES[(td[1] || r.m || '').toLowerCase().trim()];
    if (!anio || !mes) { filas.push({ slug, ym: null, td, url: r.url }); continue; }
    filas.push({
      slug, ym: ym(anio[0], mes), numero: td[2] || '', fecha: td[3] || '', denominacion: td[4] || '',
      publicado: td[6] || '', url: r.url,
    });
  }
  return filas;
}

// Requínoa publica en su propio sitio; el Portal solo enlaza a él. Patrón observado en octubre 2026.
function requinoa() {
  const filas = [];
  const hoy = new Date();
  for (let y = 2025; y <= hoy.getFullYear(); y++) {
    for (let m = 1; m <= 12; m++) {
      const k = ym(y, m);
      if (k < DESDE || new Date(y, m - 1, 1) >= new Date(hoy.getFullYear(), hoy.getMonth(), 1)) continue;
      const mes = MES_TXT[m];
      const nom = mes.charAt(0) + mes.slice(1).toLowerCase();
      filas.push({
        slug: 'requinoa', ym: k, numero: '', fecha: '', denominacion: 'URL inferida del patrón del sitio', publicado: '',
        url: `https://transparenciarequinoa.cl/nueweb/tact/requinoa/${y}/Dom/${nom}/Cumplimiento%20articulo%20116%20bis/${String(m).padStart(2, '0')}_${mes}_${y}.pdf`,
        inferida: true,
      });
    }
  }
  return filas;
}

(async () => {
  const pedidas = process.argv.slice(2);
  const slugs = Object.keys(codigos).filter((s) => !pedidas.length || pedidas.includes(s));
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ locale: 'es-CL' });
  const manifiesto = [];
  const informe = {};
  let i = 0;

  async function trabajador() {
    const page = await ctx.newPage();
    await page.goto('https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/?org=MU260', { waitUntil: 'domcontentloaded', timeout: 90000 });
    while (i < slugs.length) {
      const slug = slugs[i++];
      let res = null;
      for (let intento = 1; intento <= 2 && !res; intento++) {
        try {
          res = await page.evaluate(`(${paginaSrc})(${JSON.stringify(codigos[slug])})`);
        } catch (e) {
          console.error(`${slug}: intento ${intento} falló: ${e.message.slice(0, 120)}`);
          await page.goto('https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/?org=MU260', { waitUntil: 'domcontentloaded', timeout: 90000 }).catch(() => {});
        }
      }
      if (!res) { informe[slug] = { filas: 0, notas: ['error de ejecución'] }; continue; }
      const filas = normalizar(slug, res);
      manifiesto.push(...filas);
      informe[slug] = { filas: filas.length, sin_mes: filas.filter((f) => !f.ym).length, notas: res.notas, enlaces_externos: res.ext };
      console.log(`${slug}: ${filas.length} documentos${res.notas.length ? ' · ' + res.notas.slice(0, 2).join(' | ') : ''}`);
    }
  }
  await Promise.all([trabajador(), trabajador(), trabajador(), trabajador()]);
  await browser.close();

  if (slugs.includes('requinoa') && !manifiesto.some((f) => f.slug === 'requinoa' && f.ym)) {
    manifiesto.push(...requinoa());
    informe.requinoa = { filas: manifiesto.filter((f) => f.slug === 'requinoa').length, notas: ['Enlaces inferidos del patrón de transparenciarequinoa.cl; si alguno da 404 se informa en la descarga'] };
  }
  manifiesto.sort((a, b) => (a.slug + (a.ym || '')).localeCompare(b.slug + (b.ym || '')));

  // Si se pidieron solo algunas comunas, se conserva el resto del manifiesto anterior.
  const ruta = path.join(RAIZ, 'data/manifiesto.json');
  let final = manifiesto, inf = informe;
  if (pedidas.length && fs.existsSync(ruta)) {
    const prev = JSON.parse(fs.readFileSync(ruta, 'utf8'));
    final = prev.filter((f) => !slugs.includes(f.slug)).concat(manifiesto);
    const ip = path.join(RAIZ, 'data/portal_informe.json');
    inf = Object.assign(fs.existsSync(ip) ? JSON.parse(fs.readFileSync(ip, 'utf8')) : {}, informe);
  }
  fs.writeFileSync(ruta, JSON.stringify(final, null, 1));
  fs.writeFileSync(path.join(RAIZ, 'data/portal_informe.json'), JSON.stringify(inf, null, 1));
  console.log(`Manifiesto: ${final.length} documentos en ${new Set(final.map((f) => f.slug)).size} comunas`);
})();
