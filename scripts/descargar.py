"""Descarga los PDF listados en data/manifiesto.json (lo genera scripts/portal.js).

Guarda cada documento como pdfs/<comuna>/<AAAA-MM>.pdf (si el mes tiene varios documentos:
<AAAA-MM>_2.pdf, _3.pdf…) y, al lado, un .url con el enlace original, que el dashboard usa
como "Abrir documento". Si el archivo ya existe NO se vuelve a bajar: cada mes solo entra lo nuevo.

Maneja los enlaces de Google Drive/Docs, que son los más usados por los municipios.
Siempre escribe data/descarga_informe.json con lo descargado, lo que ya estaba y lo que falló
(y por qué), para que ninguna comuna quede "sin datos" sin que se sepa la razón.

Uso: python scripts/descargar.py [--desde AAAA-MM] [comuna ...]
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
# Algunos sitios municipales responden distinto según el "navegador" que se declara: se prueban varios.
UAS = [UA, "Mozilla/5.0 (compatible; CChC-OHiggins-Estudios/1.0)", "node", "curl/8.5.0"]
MAX_BYTES = 80 * 1024 * 1024


def pedir(url, intentos=3, timeout=90, ua=UA):
    """Devuelve (bytes, content_type) o lanza la última excepción."""
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                datos = r.read(MAX_BYTES + 1)
                if len(datos) > MAX_BYTES:
                    raise ValueError("archivo mayor a 80 MB")
                return datos, r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code in (400, 401, 403, 404, 410):
                break
        except Exception as e:  # noqa: BLE001
            ultimo = e
        time.sleep(2 * (i + 1))
    raise ultimo


def id_drive(url):
    m = re.search(r"drive\.google\.com/file/d/([\w-]+)", url) or re.search(r"[?&]id=([\w-]+)", url)
    return m.group(1) if m and "drive.google.com" in url else None


def candidatos(url):
    """Lista de URL a probar para obtener el PDF real detrás de un enlace del Portal."""
    u = url.replace(" ", "%20")
    fid = id_drive(u)
    if fid:
        return [
            f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t",
            f"https://drive.google.com/uc?export=download&id={fid}",
        ]
    m = re.search(r"docs\.google\.com/document/d/([\w-]+)", u)
    if m:
        return [f"https://docs.google.com/document/d/{m.group(1)}/export?format=pdf"]
    if "drive.google.com/drive/folders" in u:
        return []  # carpeta: no se puede bajar un único PDF
    if "sharepoint.com" in u:
        return [u + ("&" if "?" in u else "?") + "download=1", u]
    return [u]


def bajar(url):
    errores = []
    for c in candidatos(url):
        for ua in UAS:
            try:
                datos, _ = pedir(c, intentos=2, ua=ua)
            except Exception as e:  # noqa: BLE001
                errores.append(f"{type(e).__name__}: {str(e)[:80]}")
                continue
            if datos[:5] == b"%PDF-":
                return datos, None
            errores.append("la respuesta no es un PDF (¿requiere iniciar sesión o es imagen/Word?)")
    if not candidatos(url):
        errores.append("el enlace apunta a una carpeta de Drive")
    return None, "; ".join(dict.fromkeys(errores)) or "sin respuesta"


def guardar_texto(pdf):
    """Deja al lado del PDF un .txt con el texto de cada página (sirve para leer sin abrir el PDF)."""
    try:
        from pypdf import PdfReader
        rd = PdfReader(str(pdf))
        partes = []
        for i, pg in enumerate(rd.pages[:600], 1):
            try:
                t = (pg.extract_text() or "").strip()
            except Exception:  # noqa: BLE001
                t = ""
            partes.append(f"=== página {i} ===\n{t}")
        pdf.with_suffix(".txt").write_text("\n".join(partes), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  (sin texto para {pdf.name}: {type(e).__name__})")


def main():
    args = sys.argv[1:]
    desde = "2025-05"
    if "--desde" in args:
        i = args.index("--desde")
        desde = args[i + 1]
        del args[i:i + 2]
    pedidas = set(args)

    # Configuración opcional (data/descarga_config.json): {"desde": "2026-10", "max_mb": 300}
    # Permite controlar desde el repositorio desde qué mes se descarga y cuánto pesa cada ejecución.
    # Opcionales: "hasta": "2026-09" (último mes a bajar) y "limpiar": true (borra los PDF de los meses que ya
    # tienen su archivo en data/crudo/, para que el repositorio no crezca sin límite; el .txt y el .url se conservan).
    max_bytes_run = None
    hasta = "9999-12"
    limpiar = False
    cfg = RAIZ / "data" / "descarga_config.json"
    if cfg.exists():
        c = json.loads(cfg.read_text(encoding="utf-8"))
        desde = c.get("desde", desde)
        hasta = c.get("hasta", hasta)
        limpiar = bool(c.get("limpiar"))
        if c.get("max_mb"):
            max_bytes_run = int(c["max_mb"]) * 1024 * 1024
    if limpiar:
        borrados = 0
        for pdf in sorted((RAIZ / "pdfs").glob("*/*.pdf")):
            if (RAIZ / "data" / "crudo" / f"{pdf.parent.name}_{pdf.stem.split('_')[0]}.json").exists():
                pdf.unlink()
                borrados += 1
        print(f"Limpieza: {borrados} PDF ya procesados borrados")
    print(f"Descargando desde {desde} hasta {hasta}" + (f" (tope {max_bytes_run // 1048576} MB por ejecución)" if max_bytes_run else ""))
    total_bytes = 0

    ruta = RAIZ / "data" / "manifiesto.json"
    if not ruta.exists():
        sys.exit("Falta data/manifiesto.json: ejecuta antes `node scripts/portal.js`.")
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))

    por_mes = defaultdict(list)
    sin_mes = defaultdict(int)
    for f in manifiesto:
        if pedidas and f["slug"] not in pedidas:
            continue
        if not f.get("url") or not f["url"].startswith("http"):
            sin_mes[f["slug"]] += 0
            continue
        if not f.get("ym"):
            sin_mes[f["slug"]] += 1
            continue
        if f["ym"] < desde or f["ym"] > hasta:
            continue
        por_mes[(f["slug"], f["ym"])].append(f)

    informe = {}
    for (slug, ym), docs in sorted(por_mes.items()):
        carpeta = RAIZ / "pdfs" / slug
        carpeta.mkdir(parents=True, exist_ok=True)
        r = informe.setdefault(slug, {"descargados": 0, "ya_estaban": 0, "fallidos": []})
        vistos = set()
        n = 0
        for d in docs:
            if d["url"] in vistos:
                continue
            vistos.add(d["url"])
            n += 1
            nombre = ym if n == 1 else f"{ym}_{n}"
            pdf = carpeta / f"{nombre}.pdf"
            if pdf.exists() or pdf.with_suffix(".url").exists():
                r["ya_estaban"] += 1
                continue
            if max_bytes_run and total_bytes >= max_bytes_run:
                r.setdefault("pendientes_por_tope", []).append(nombre)
                continue
            datos, err = bajar(d["url"])
            if datos is None:
                r["fallidos"].append({"mes": nombre, "url": d["url"], "motivo": err})
                print(f"  ✗ {slug} {nombre}: {err}")
                continue
            pdf.write_bytes(datos)
            pdf.with_suffix(".url").write_text(d["url"], encoding="utf-8")
            total_bytes += len(datos)
            guardar_texto(pdf)
            r["descargados"] += 1
            print(f"  ✓ {slug} {nombre} ({len(datos)//1024} KB)")
    for slug, n in sin_mes.items():
        if n:
            informe.setdefault(slug, {"descargados": 0, "ya_estaban": 0, "fallidos": []})["filas_sin_mes_identificable"] = n

    (RAIZ / "data" / "descarga_informe.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(v["descargados"] for v in informe.values())
    fal = sum(len(v["fallidos"]) for v in informe.values())
    print(f"Listo: {tot} PDF nuevos, {fal} fallidos, {sum(v['ya_estaban'] for v in informe.values())} ya estaban.")


if __name__ == "__main__":
    main()
