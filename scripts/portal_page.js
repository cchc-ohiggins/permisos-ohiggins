// Código que se ejecuta DENTRO de una página de portaltransparencia.cl (lo usa scripts/portal.js).
// Es la función que se validó a mano en el navegador con las comunas de la región.
// Recibe el código de organismo (p. ej. "MU260") y devuelve {code, rows, notas, ext}.
// Cada fila: {y, m, td:[Año, Mes, N°, Fecha, Denominación, Descripción, Publicación, ...], url}
async (code) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const waitFor = async (fn, ms = 9000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      try { const v = fn(); if (v) return v; } catch (e) {}
      await sleep(250);
    }
    return null;
  };
  const MESES = /^(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)$/i;
  const re116 = /permisos y autorizaciones del Art\. 116 bis C/i;
  const yrRe = /(2025|2026|2027)\s*$/;

  async function abrirFicha() {
    const f = document.createElement('iframe');
    f.style.cssText = 'width:1000px;height:800px;position:fixed;left:-3000px;top:0';
    document.body.appendChild(f);
    await new Promise((res) => { f.onload = res; f.src = '/PortalPdT/directorio-de-organismos-regulados/?org=' + code; });
    await sleep(1200);
    return f;
  }
  function filas(d) {
    const out = [];
    d.querySelectorAll('tr').forEach((tr) => {
      const td = [...tr.querySelectorAll('td')].map((x) => x.innerText.trim().replace(/\s+/g, ' '));
      const as = [...tr.querySelectorAll('a[href]')].filter(
        (a) => /^https?:/i.test(a.href) && !/portaltransparencia\.cl\/PortalPdT\/directorio/.test(a.href));
      if (td.length >= 4 && (as.length || td.length >= 7)) out.push({ td: td.slice(0, 8), url: as[0] ? as[0].href : null });
    });
    return out;
  }
  const textos = (d, sel) => [...new Set([...d.querySelectorAll(sel)].map((a) => a.textContent.trim()))];
  const aniosDe = (d) => {
    const tabs = textos(d, 'a.tab-link').filter((t) => yrRe.test(t));
    const sueltos = textos(d, 'a').filter((t) => /^Permisos y Autorizaciones 20\d\d$/.test(t) && !tabs.includes(t));
    return tabs.concat(sueltos);
  };
  const mesesDe = (d) => textos(d, 'a.tab-link, a').filter((t) => MESES.test(t));
  const buscar = (d, s) => [...d.querySelectorAll('a')].find((x) => x.textContent.trim() === s);

  async function abrir116() {
    const f = await abrirFicha();
    const d = f.contentDocument;
    const l = await waitFor(() => [...d.querySelectorAll('a')].find((a) => re116.test(a.textContent)), 6000);
    if (!l) { f.remove(); return null; }
    l.click();
    await waitFor(() => d.querySelector('a.tab-link') || filas(d).length || d.querySelector('table'), 9000);
    await sleep(800);
    return { f, d };
  }
  async function clic(d, s) {
    const a = await waitFor(() => buscar(d, s), 9000);
    if (!a) return false;
    a.click();
    await sleep(2500);
    await waitFor(() => filas(d).length || mesesDe(d).length, 8000);
    return true;
  }

  const res = { code, rows: [], notas: [], ext: [] };
  const p = await abrir116();
  if (!p) { res.notas.push('sin ítem 116 bis C en el Portal'); return res; }
  const anios = aniosDe(p.d);
  const meses0 = mesesDe(p.d);
  const directas = filas(p.d);
  res.ext = [...p.d.querySelectorAll('a[href]')]
    .filter((a) => /^https?:/.test(a.href) && !/portaltransparencia\.cl|consejotransparencia\.cl/.test(a.href))
    .map((a) => a.href).slice(0, 3);
  p.f.remove();

  // 1) Tabla directamente en el ítem (p. ej. Peumo)
  if (directas.length) res.rows.push(...directas.map((r) => ({ y: '', ...r })));

  // 2) Pestañas de año (con filas o con un nivel extra de meses)
  for (const y of anios) {
    const q = await abrir116();
    if (!q) { res.notas.push(y + ': no se pudo reabrir'); continue; }
    let rows = [], ms = [];
    try {
      if (!(await clic(q.d, y))) { res.notas.push(y + ': pestaña no clicable'); q.f.remove(); continue; }
      rows = filas(q.d);
      ms = mesesDe(q.d);
    } catch (e) { res.notas.push(y + ': ' + e); }
    q.f.remove();
    if (rows.length) { res.rows.push(...rows.map((r) => ({ y, ...r }))); continue; }
    if (!ms.length) { res.notas.push(y + ': sin filas ni meses'); continue; }
    for (const m of ms) {
      const z = await abrir116();
      if (!z) continue;
      try {
        await clic(z.d, y);
        await clic(z.d, m);
        const r2 = filas(z.d);
        if (r2.length) res.rows.push(...r2.map((r) => ({ y, m, ...r })));
        else res.notas.push(y + ' ' + m + ': sin filas (¿enlace externo?)');
      } catch (e) { res.notas.push(y + ' ' + m + ': ' + e); }
      z.f.remove();
    }
  }

  // 3) Solo pestañas de mes, sin año (p. ej. Navidad)
  if (!anios.length && !directas.length && meses0.length) {
    for (const m of meses0) {
      const z = await abrir116();
      if (!z) continue;
      try {
        await clic(z.d, m);
        const r2 = filas(z.d);
        if (r2.length) res.rows.push(...r2.map((r) => ({ y: '', m, ...r })));
        else res.notas.push(m + ': sin filas');
      } catch (e) { res.notas.push(m + ': ' + e); }
      z.f.remove();
    }
  }
  if (!res.rows.length && !res.notas.length) res.notas.push('ítem 116 bis C sin contenido publicado');
  return res;
}
