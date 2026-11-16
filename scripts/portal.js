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


// --- DIAGNÓSTICO: deja en data/portal_debug.json lo que ve el robot al abrir el Portal desde GitHub ---
async function diagnostico(browser) {
  const dbg = { fecha: new Date().toISOString() };
  try {
    const c = await browser.newContext({ locale: 'es-CL' });
    const pg = await c.newPage();
    const resp = await pg.goto('https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/?org=MU260', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await pg.waitForTimeout(6000);
    dbg.portal = { status: resp ? resp.status() : null, url: pg.url(), titulo: await pg.title(), texto: (await pg.evaluate(() => document.body.innerText)).replace(/\s+/g, ' ').slice(0, 700), enlaces116: await pg.evaluate(() => [...document.querySelectorAll('a')].filter((a) => /116 bis C/i.test(a.textContent)).length) };
    fs.mkdirSync(path.join(RAIZ, 'data/debug'), { recursive: true });
    await pg.screenshot({ path: path.join(RAIZ, 'data/debug/portal.png') });
  } catch (e) { dbg.portal = { error: String(e.message).slice(0, 300) }; }
  for (const [k, u] of [['requinoa_pdf', 'https://transparenciarequinoa.cl/nueweb/tact/requinoa/2026/Dom/Enero/Cumplimiento%20articulo%20116%20bis/01_ENERO_2026.pdf'], ['requinoa_home', 'https://transparenciarequinoa.cl/'], ['portal_home', 'https://www.portaltransparencia.cl/']]) {
    try {
      const r = await fetch(u, { redirect: 'follow', signal: AbortSignal.timeout(30000) });
      const b = Buffer.from(await r.arrayBuffer());
      dbg[k] = { status: r.status, tipo: r.headers.get('content-type'), bytes: b.length, inicio: b.slice(0, 160).toString('latin1').replace(/\s+/g, ' ') };
    } catch (e) { dbg[k] = { error: String(e.message).slice(0, 200), causa: e.cause ? String(e.cause.code || e.cause.message).slice(0, 120) : null }; }
  }
  fs.writeFileSync(path.join(RAIZ, 'data/portal_debug.json'), JSON.stringify(dbg, null, 1));
}

(async () => {
  const pedidas = process.argv.slice(2);
  const slugs = Object.keys(codigos).filter((s) => !pedidas.length || pedidas.includes(s));
  const browser = await chromium.launch();
  await diagnostico(browser);
  const ctx = await browser.newContext({ locale: 'es-CL' });
  const manifiesto = [];
  const informe = {};
  let i = 0;

  async function trabajador() {
    const page = await ctx.newPage();
    await page.goto('https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/?org=MU260', { waitUntil: 'domcontentloaded',
