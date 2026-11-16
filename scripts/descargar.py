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
MAX_BYTES = 80 * 1024 * 1024


def pedir(url, intentos=3, timeout=90):
    """Devuelve (bytes, content_type) o lanza la última excepción."""
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
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
        try:
            datos, _ = pedir(c)
        except Exception as e:  # noqa: BLE001
            errores.append(f"{type(e).__name__}: {str(e)[:80]}")
            continue
        if datos[:5] == b"%PDF-":
            return datos, None
        errores.append("la respuesta no es un PDF (¿requiere iniciar sesión o es imagen/Word?)")
    if not candidatos(url):
        errores.append("el enlace apunta a una carpeta de Drive")
    return None, "; ".join(dict.fromkeys(errores)) or "sin respuesta"


def main():
    args = sys.argv[1:]
    desde = "2025-05"
    if "--desde" in args:
        i = args.index("--desde")
        desde = args[i + 1]
        del args[i:i + 2]
    pedidas = set(args)

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
        if f["ym"] < desde:
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
            if pdf.exists():
                r["ya_estaban"] += 1
                continue
            datos, err = bajar(d["url"])
            if datos is None:
                r["fallidos"].append({"mes": nombre, "url": d["url"], "motivo": err})
                print(f"  ✗ {slug} {nombre}: {err}")
                continue
            pdf.write_bytes(datos)
            pdf.with_suffix(".url").write_text(d["url"], encoding="utf-8")
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
