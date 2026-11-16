// El Portal de Transparencia bloquea (403) a los servidores de GitHub, así que este paso ya no lee el Portal.
// El listado (data/manifiesto.json) lo arma Claude desde el navegador del computador de la CChC
// con la función de scripts/portal_page.js y lo sube al repositorio. Este archivo solo evita romper el flujo.
console.log('portal.js: se usa data/manifiesto.json tal como está en el repositorio (lo sube Claude cada mes).');
