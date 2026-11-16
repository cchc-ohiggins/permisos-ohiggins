#!/usr/bin/env python3
"""Convierte los PDF de permisos de edificación en registros estructurados.

Entrada : pdfs/<comuna>/<AAAA-MM>.pdf   (resolución mensual de la DOM + copias de los permisos)
          pdfs/<comuna>/<AAAA-MM>.url   (opcional: link original del documento, una línea)
Salida  : data/crudo/<comuna>_<AAAA-MM>.json

Uso:
  python scripts/extraer.py                         # procesa todo lo que aún no está extraído
  python scripts/extraer.py --solo rancagua         # una comuna
  python scripts/extraer.py --solo rancagua --mes 2026-03 --rehacer

Requiere la variable de entorno ANTHROPIC_API_KEY.
"""
import argparse, base64, io, json, os, re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PDFS = RAIZ / "pdfs"
CRUDO = RAIZ / "data" / "crudo"
MODELO = os.environ.get("MODELO_EXTRACCION", "claude-sonnet-5-5")
PAGINAS_POR_TANDA = 12

PROMPT = """Eres analista de datos de la Cámara Chilena de la Construcción. El documento adjunto es la publicación mensual
de permisos y autorizaciones de la Dirección de Obras Municipales (DOM) de la comuna de {comuna}, correspondiente al mes {mes}
(Art. 116 bis C de la LGUC). Puede traer un listado resumen y/o copias escaneadas de cada permiso.
Este fragmento corresponde a las páginas {desde} a {hasta} del documento completo (la primera página del fragmento es la {desde}).

Extrae UN registro por cada permiso o autorización distinta y devuelve SOLO un arreglo JSON (sin texto adicional) con objetos de esta forma:
{{
  "numero": "N° del permiso/autorización tal como aparece (texto)",
  "fecha": "AAAA-MM-DD o null",
  "tipo_original": "tipo tal como aparece (ej: Permiso de edificación obra nueva, Modificación de proyecto, Recepción definitiva, Obra menor...)",
  "destino": "destino tal como aparece (vivienda, comercio, industria, equipamiento...) o null",
  "proyecto": "nombre del proyecto o null",
  "descripcion": "descripción de las obras tal como aparece (ej: 'construcción de 24 viviendas pareadas de 2 pisos'), máximo 300 caracteres, o null",
  "direccion": "dirección del predio (calle, número, villa/lote) o null",
  "rol": "rol de avalúo SII (ej: 635-160) o null",
  "superficie_m2": número con la superficie total edificada en m² SOLO si aparece explícita, o null,
  "superficie_terreno_m2": número con la superficie del terreno/predio en m² SOLO si aparece explícita, o null,
  "pisos": número entero de pisos SOLO si aparece explícito, o null,
  "presupuesto": "presupuesto de obra tal como aparece (con su unidad: $, UF) o null",
  "viviendas": número entero de viviendas/unidades SOLO si aparece explícito, o null,
  "propietario": "propietario o empresa solicitante tal como aparece, o null",
  "arquitecto": "arquitecto o profesional responsable, o null",
  "constructora": "empresa constructora, o null",
  "pagina": número de página (del documento completo) donde aparece el permiso o su listado
}}

Cómo leer los formularios reales (aprendido de documentos de Rancagua, Machalí y Requínoa):
- Un mismo PDF puede traer (a) una resolución con anexo-listado de permisos y (b) las copias escaneadas de cada permiso (formularios 2-4.1 obra nueva, 2-4.2 ampliación, 2-6.x modificación de proyecto, 1-2.x obra menor, 12.x certificado de regularización, certificados de recepción). Devuelve un solo registro por permiso, combinando listado y copia.
- "superficie_m2": en permisos de obra nueva/ampliación es "Superficie edificada total"; en certificados de regularización es la superficie a regularizar/regularizada.
- "superficie_terreno_m2": «Superficie total del predio» (sección 6.1) o «Superficie del terreno».
- "viviendas": solo desde «Número de unidades totales por destino → Viviendas» o frases como «16 viviendas»; «una vivienda» = 1. No lo deduzcas de la superficie.
- "presupuesto": monto del «Presupuesto» en la sección de derechos municipales, con su unidad.
- "proyecto": «Nombre del proyecto». En certificados de regularización normalmente no existe: usa null.
- "propietario": razón social o nombre del propietario/solicitante. Es posible que el municipio tape datos con un recuadro; si no se lee, usa null.
- "tipo_original": respeta el tipo del documento (p. ej. «Certificado de regularización», «Permiso de edificación obra nueva», «Modificación de proyecto de edificación»).
- No mezcles datos de dos permisos: cada formulario tiene su propio número de permiso, fecha y rol en el encabezado.

Reglas estrictas:
- No inventes ni infieras datos. Si un campo no aparece de forma explícita, usa null.
- "superficie_m2" es la superficie edificada; "superficie_terreno_m2" es la del predio. No las confundas entre sí ni con montos en pesos.
- "propietario" es quien solicita el permiso (persona o empresa); no lo confundas con arquitecto ni constructora.
- Si un mismo permiso aparece en el listado y en su copia, devuelve un solo registro combinando los datos.
- Si el fragmento no contiene permisos (portada, oficios, etc.), devuelve [].
"""


def cargar_pypdf():
    try:
        from pypdf import PdfReader, PdfWriter
        return PdfReader, PdfWriter
    except ImportError:
        sys.exit("Falta pypdf: pip install -r requirements.txt")


def tandas(pdf_path):
    """Divide el PDF en fragmentos de PAGINAS_POR_TANDA páginas. Devuelve (desde, hasta, bytes)."""
    PdfReader, PdfWriter = cargar_pypdf()
    lector = PdfReader(str(pdf_path))
    total = len(lector.pages)
    for ini in range(0, total, PAGINAS_POR_TANDA):
        fin = min(ini + PAGINAS_POR_TANDA, total)
        w = PdfWriter()
        for i in range(ini, fin):
            w.add_page(lector.pages[i])
        buf = io.BytesIO()
        w.write(buf)
        yield ini + 1, fin, buf.getvalue()


def parsear_lista_json(texto):
    """Extrae el primer arreglo JSON de la respuesta del modelo (tolera ```json ... ```)."""
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.S)
    ini, fin = texto.find("["), texto.rfind("]")
    if ini == -1 or fin == -1:
        raise ValueError("La respuesta no contiene un arreglo JSON")
    datos = json.loads(texto[ini:fin + 1])
    if not isinstance(datos, list):
        raise ValueError("La respuesta no es una lista")
    return [d for d in datos if isinstance(d, dict)]


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d[\d.,]*", str(v))            # solo el primer número ("85,2 m2" -> "85,2")
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if s.count(",") == 1 and s.count(".") >= 1:      # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") == 1:                            # 1234,56
        s = s.replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):   # 1.234.567 ó 1.250 (punto = miles, uso chileno)
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def limpiar(reg):
    """Normaliza tipos de un registro devuelto por el modelo."""
    txt = lambda k: (str(reg.get(k)).strip() or None) if reg.get(k) not in (None, "") else None
    viv = _num(reg.get("viviendas"))
    pag = _num(reg.get("pagina"))
    pis = _num(reg.get("pisos"))
    return {
        "numero": txt("numero"), "fecha": txt("fecha"), "tipo_original": txt("tipo_original"),
        "destino": txt("destino"), "proyecto": txt("proyecto"), "direccion": txt("direccion"),
        "descripcion": (txt("descripcion") or "")[:300] or None, "presupuesto": txt("presupuesto"),
        "pisos": int(pis) if pis is not None else None,
        "superficie_terreno_m2": _num(reg.get("superficie_terreno_m2")),
        "rol": txt("rol"), "superficie_m2": _num(reg.get("superficie_m2")),
        "viviendas": int(viv) if viv is not None else None,
        "propietario": txt("propietario"), "arquitecto": txt("arquitecto"),
        "constructora": txt("constructora"), "pagina": int(pag) if pag is not None else None,
    }


def fusionar(registros):
    """Une registros repetidos (mismo número y tipo) que aparecen en distintas tandas, completando campos vacíos."""
    por_clave = {}
    for r in registros:
        clave = ((r.get("numero") or "").lower(), (r.get("tipo_original") or "").lower())
        if not clave[0]:                    # sin número: se conserva tal cual
            clave = ("", f"{len(por_clave)}")
        if clave in por_clave:
            base = por_clave[clave]
            for k, v in r.items():
                if base.get(k) is None and v is not None:
                    base[k] = v
        else:
            por_clave[clave] = dict(r)
    return list(por_clave.values())


def llamar_modelo(cliente, pdf_bytes, comuna, mes, desde, hasta):
    b64 = base64.standard_b64encode(pdf_bytes).decode()
    msg = cliente.messages.create(
        model=MODELO, max_tokens=8000,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
            {"type": "text", "text": PROMPT.format(comuna=comuna, mes=mes, desde=desde, hasta=hasta)},
        ]}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def procesar(cliente, slug, nombre, mes, pdf_path):
    registros, errores = [], []
    for desde, hasta, datos in tandas(pdf_path):
        try:
            texto = llamar_modelo(cliente, datos, nombre, mes, desde, hasta)
            registros += [limpiar(r) for r in parsear_lista_json(texto)]
        except Exception as e:  # una tanda con problemas no debe tumbar el resto
            errores.append(f"páginas {desde}-{hasta}: {e}")
    url_path = pdf_path.with_suffix(".url")
    url = url_path.read_text().strip() if url_path.exists() else None
    return {"comuna": nombre, "slug": slug, "mes": mes, "archivo": pdf_path.name,
            "documento_url": url, "registros": fusionar(registros), "errores": errores}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="slug de una comuna (ej: rancagua)")
    ap.add_argument("--mes", help="AAAA-MM")
    ap.add_argument("--rehacer", action="store_true", help="vuelve a extraer aunque exista salida")
    ap.add_argument("--max", type=int, default=0, help="máximo de documentos por ejecución (0 = sin límite); lo pendiente se hace en la siguiente")
    a = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Falta la variable de entorno ANTHROPIC_API_KEY")
    try:
        import anthropic
    except ImportError:
        sys.exit("Falta anthropic: pip install -r requirements.txt")
    cliente = anthropic.Anthropic()

    comunas = {c["slug"]: c["nombre"] for c in json.loads((RAIZ / "data" / "comunas.json").read_text())["comunas"]}
    CRUDO.mkdir(parents=True, exist_ok=True)
    hechos = 0
    for pdf in sorted(PDFS.glob("*/*.pdf")):
        slug, mes = pdf.parent.name, pdf.stem[:7]
        if slug not in comunas or not re.fullmatch(r"\d{4}-\d{2}", mes):
            print(f"Omitido (nombre no reconocido): {pdf}")
            continue
        if (a.solo and slug != a.solo) or (a.mes and mes != a.mes):
            continue
        salida = CRUDO / f"{slug}_{pdf.stem}.json"
        if salida.exists() and not a.rehacer:
            continue
        if a.max and hechos >= a.max:
            print(f"Límite de {a.max} documentos por ejecución alcanzado; el resto queda para la próxima.")
            break
        print(f"Extrayendo {comunas[slug]} {mes} …")
        res = procesar(cliente, slug, comunas[slug], mes, pdf)
        salida.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print(f"  {len(res['registros'])} registros, {len(res['errores'])} tandas con error")
        hechos += 1
    print(f"Listo: {hechos} documento(s) procesado(s).")


if __name__ == "__main__":
    main()
