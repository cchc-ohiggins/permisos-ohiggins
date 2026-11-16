# Permisos de edificación · Región de O'Higgins

Panel web de la CChC O'Higgins (Estudios) que reúne los permisos y autorizaciones que las 33 Direcciones de Obras Municipales
publican cada mes en Transparencia Activa (Art. 116 bis C de la LGUC, Ley 21.718), con filtros, gráficos, mapa y link al documento original.

## Cómo funciona

```
Portal Transparencia ─► scripts/portal.js ─► data/manifiesto.json ─► scripts/descargar.py ─► pdfs/<comuna>/AAAA-MM.pdf
 (33 comunas, art. 116 bis C)   (navegador automático)   (comuna, mes, N° resolución, enlace)    (solo lo nuevo)
                                                                                                     │
index.html ◄─ data/permisos.json ◄─ scripts/construir.py ◄─ data/crudo/*.json ◄─ scripts/extraer.py ◄┘
 (socios)      (normaliza, geocodifica)   (por comuna y mes)        (lectura del PDF con IA)
```

Todo esto lo ejecuta solo **GitHub Actions** (`.github/workflows/actualizar.yml`) los **días 10 y 20 de cada mes**: los municipios deben publicar
hasta el 5° día hábil, pero varios se atrasan, y como solo se procesa lo nuevo, repetir no cuesta casi nada. También se puede lanzar a mano (*Actions → Run workflow*).

1. **Portal** (`portal.js`): entra a la ficha de cada comuna en portaltransparencia.cl (códigos en `data/portal_codigos.json`), abre el ítem
   «Actos y resoluciones con efectos sobre terceros → DOM – permisos y autorizaciones del Art. 116 bis C LGUC», recorre las pestañas de año (y de mes cuando existen) y registra el enlace de cada documento.
   Desde **mayo de 2025** (entrada en vigencia de la Ley 21.718) hasta hoy. Deja `data/manifiesto.json` y `data/portal_informe.json` (qué encontró en cada comuna y qué no).
2. **Descarga** (`descargar.py`): baja cada PDF a `pdfs/<comuna>/<AAAA-MM>.pdf` con un `.url` al lado (el enlace original, que el panel usa como «Abrir documento»). Entiende Google Drive/Docs, que usan muchos municipios. Lo que no pudo bajar queda con el motivo en `data/descarga_informe.json`.
   El mes es el de **otorgamiento** de los permisos (la resolución publicada en junio trae los de mayo → `2026-05.pdf`).
3. **Extracción** (`extraer.py`): lee cada PDF en tandas de 12 páginas con Claude y devuelve un registro por permiso (N°, fecha, tipo, destino, proyecto, descripción, dirección, rol, m² construidos, m² de terreno, pisos, presupuesto, viviendas, empresa, constructora). No inventa datos: lo que no aparece queda vacío. Procesa solo los PDF que aún no tienen salida y, en la carga inicial, hasta 60 por ejecución (parámetro `max_documentos`).
4. **Construcción** (`construir.py`): clasifica el tipo de permiso, normaliza el destino, geocodifica la dirección (OpenStreetMap) y calcula la **cobertura** (qué comunas y meses tienen datos).
5. **Panel** (`index.html`): filtros por año, mes, comuna, tipo y destino; alertas de proyectos grandes; **matriz mes a mes de las 33 comunas** (cuántos permisos hay, qué documentos están publicados aún sin leer y cuáles no existen, con el motivo); mapa, gráficos, rankings y detalle con enlace al documento. Si `data/permisos.json` está vacío, muestra `data/demo.json` (registros ficticios, generados con `scripts/generar_demo.py` sobre los meses realmente publicados) con una franja de aviso. La matriz lee `data/publicacion.json`, que `construir.py` regenera desde el manifiesto del Portal.
6. **Hoja de análisis** (`analisis.html`): segunda hoja, para control de gestión. Tendencia mensual por destino, reparto vivienda/comercio por trimestre, tipos de documento, tabla de comunas con variación (últimos 3 meses vs 3 anteriores y vs el mismo período del año anterior, solo con comunas que publicaron todos los meses comparados), tamaño de proyectos, empresas y calidad de los datos. Usa los mismos datos que el panel y no requiere nada más. Desde cada comuna hay un enlace al panel con la comuna y el período ya filtrados (`index.html?comuna=Rancagua&desde=2026-01&hasta=2026-06`).
7. **Mapa**: límites comunales en `data/limites.json` (división político-administrativa, tomada de github.com/caracena/chile-geojson y simplificada). Mosaicos de OpenStreetMap, que no piden clave (el proveedor anterior, CARTO, ahora exige una).

## Puesta en marcha (una sola vez)

1. En GitHub, crea el repositorio `permisos-ohiggins` en la cuenta `cchc-ohiggins` y sube todo el contenido de esta carpeta (incluida la carpeta oculta `.github`).
2. **Settings → Pages → Deploy from a branch → `main` / `(root)`** para publicar el panel.
3. (Opcional, tiene costo) **Settings → Secrets and variables → Actions → New repository secret**: nombre `ANTHROPIC_API_KEY`, valor = clave de la API de Anthropic (se crea en console.anthropic.com).
4. **Actions → Actualizar permisos de edificación → Run workflow** (deja `60` en el máximo). Cada ejecución procesa hasta 60 PDF; **repite el Run workflow hasta que ya no queden pendientes** (el log dice «Listo: 0 documento(s) procesado(s)»). Esa es la carga inicial de 2025–2026.
5. Desde ahí el panel se actualiza solo. El mismo procedimiento sirve si un municipio publica con atraso: la siguiente ejecución lo recoge.

> **Costo de la IA**: la lectura de los PDF consume la API de Anthropic. La carga inicial (unos 450 documentos, algunos de cientos de páginas) es la parte cara; después solo entran los PDF nuevos de cada mes. Revisa el consumo en console.anthropic.com tras las primeras ejecuciones.

## Alertas y filtros (pensado para socios y para Estudios)

- **Filtro principal**: por defecto se muestran los permisos de edificación (obra nueva y modificación/ampliación). Las **regularizaciones** (viviendas existentes, Ley 20.898) y «Otros» (recepciones, subdivisiones, obras menores) se activan aparte.
- **Alertas: grandes proyectos** (solo obra nueva y ampliaciones): ≥ 50 viviendas; industria/bodegas ≥ 1.000 m²; comercio y servicios o equipamiento ≥ 1.000 m²; vivienda sin N° de viviendas informado ≥ 3.000 m². Los umbrales se editan en el propio panel. Cada alerta lleva a su ubicación en el mapa y a su documento. Es una señal para revisar el documento, no una cifra verificada.
- **Dónde se concentra**: ranking de comunas y de empresas por N° de permisos, por m² o por viviendas.
- Abrir el panel con `?demo` al final de la dirección muestra los datos de ejemplo.

## Datos reales cargados

`data/crudo/` trae **octubre 2026** de Rancagua, Machalí y Requínoa, leídos a partir de los tres documentos de ejemplo (el listado de Requínoa y Machalí y los formularios de Rancagua). Esos registros no tienen enlace al PDF porque se recibieron como archivos adjuntos. Del archivo de Rancagua no se pudieron leer los permisos N° 257 a 265 y 291 (páginas sin texto); el panel lo avisa.

## Estado de las fuentes (verificado el 15-11-2026 en el Portal)

- **26 de las 33 comunas** publican en el Portal los enlaces mensuales a sus PDF (mayo 2025 – octubre 2026): Rancagua, Codegua, Coinco, Coltauco, Doñihue, Graneros, Las Cabras, Machalí, Malloa, Mostazal, Peumo, Pichidegua, Quinta de Tilcoco, Rengo, Pichilemu, La Estrella, Marchihue, Navidad, Paredones, San Fernando, Chépica, Chimbarongo, Nancagua, Peralillo, Pumanque y Santa Cruz. Con vacíos puntuales: Mostazal solo hasta mayo 2026, Coltauco sin dic-2025 ni oct-2026, Santa Cruz sin mayo–ago 2025 (y un enlace roto), Marchihue hasta sept-2026.
- **Requínoa** publica en su propio sitio (transparenciarequinoa.cl); `portal.js` infiere los enlaces mensuales del patrón observado en octubre 2026 (por confirmar mes a mes).
- **Sin información en el Portal**: Olivar, Litueche, Palmilla y Placilla no tienen el ítem del art. 116 bis C; Lolol tiene el ítem pero sin documentos; San Vicente tiene el ítem «Permisos y Autorizaciones 2025/2026» sin tabla ni enlaces visibles. Revisar sus sitios municipales y, si corresponde, reclamar al municipio (la SEREMI MINVU fiscaliza el cumplimiento).
- **Hosts de los PDF**: sitios municipales, Google Drive, S3, SharePoint y hasta direcciones IP (Rengo). Los enlaces de **SharePoint de Navidad** (68 resoluciones sueltas) son de invitado y probablemente no se puedan bajar sin sesión; si fallan, quedan en `descarga_informe.json`.
- Una comuna sin PDF **no** significa que no tenga permisos: el panel la muestra como «sin datos» en el período. También se puede subir un PDF a mano en `pdfs/<comuna>/<AAAA-MM>.pdf` y el resto funciona igual.

## Qué falta (hoja de ruta)

- **Revisar el primer informe** (`data/portal_informe.json` y `data/descarga_informe.json`) y resolver comuna por comuna lo que falle (enlaces rotos, SharePoint, comunas sin publicación).
- `portal.js` automatiza un recorrido que se validó a mano en el navegador; la primera ejecución en GitHub confirma que funciona igual.
- **Validación con documentos reales.** El extractor está probado con un cliente simulado, no con PDF reales. El primer mes de cada comuna hay que revisarlo a mano contra el documento.
- **Geocodificación.** Depende de que la dirección sea clara. Lo que no se puede ubicar queda en el centro de la comuna (círculo punteado en el mapa).

## Decisiones de diseño

- **Datos personales**: solo se publican nombres de empresas (SpA, Ltda., Inmobiliaria, etc.). Los nombres de personas naturales y de arquitectos se descartan al construir `permisos.json`.
- **Sin datos ≠ sin permisos**: el panel muestra cuántas comunas tienen datos en el período y avisa cuáles no.
- **Superficie y viviendas** se suman solo donde el documento las informa; el panel indica en cuántos registros las tiene.
- **Tipo de permiso**: se conserva el texto original y se agrupa en *Obra nueva*, *Modificación / ampliación* y *Otros* (recepciones, subdivisiones, obras menores, regularizaciones, etc.). Un «Permiso de edificación» sin más detalle se asume obra nueva y queda marcado como «clasificación inferida».
- **Paleta**: naranja `#E74100` (obra nueva), azul `#006EDC` (modificación / ampliación), gris `#6B7280` (otros); azul oscuro `#003D6B` para encabezados.


## Sin clave de IA (modo gratuito)
Si no se configura `ANTHROPIC_API_KEY`, el flujo igual recorre el Portal y descarga los PDF nuevos (gratis) y omite la lectura con IA. Los PDF quedan en `pdfs/` y se pueden leer en una sesión con Claude (sin costo de API) o con lectores por comuna; el resultado se guarda en `data/crudo/` y `construir.py` arma `data/permisos.json`.
