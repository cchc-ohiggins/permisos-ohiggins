#!/usr/bin/env python3
"""Une los registros extraídos (data/crudo/*.json), los normaliza, los geocodifica y escribe data/permisos.json.

Uso:
  python scripts/construir.py
  python scripts/construir.py --sin-geocodificar     # no consulta mapas (todo queda en el centro de la comuna)
"""
import argparse, hashlib, json, math, re, sys, time, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parent.parent
CRUDO = RAIZ / "data" / "crudo"
SALIDA = RAIZ / "data" / "permisos.json"
CACHE = RAIZ / "data" / "geocache.json"
RADIO_MAX_KM = 30  # un resultado más lejos que esto del centro de la comuna se considera error de geocodificación


def sin_tildes(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------- clasificación ----------
def clasificar(tipo):
    """Devuelve (categoria, inferida). Las reglas se evalúan en orden: lo más específico primero."""
    t = sin_tildes(tipo)
    if not t:
        return "otros", False
    if "recepcion" in t:
        return "recepcion", False
    if "anteproyecto" in t:
        return "anteproyecto", False
    if re.search(r"subdivision|loteo|fusion|urbanizacion|copropiedad", t):
        return "subdivision", False
    if "demolicion" in t:
        return "demolicion", False
    if "regulariz" in t:
        return "regularizacion", False
    if "obra menor" in t:
        return "obra_menor", False
    if re.search(r"modificaci|alteraci|reparaci|reconstrucci", t):
        return "modificacion", False
    if "ampliaci" in t:
        return "ampliacion", False
    if re.search(r"obra nueva|edificacion nueva|construccion nueva|\bnueva\b", t):
        return "nueva", False
    if re.search(r"permiso de edificacion|edificacion", t):
        return "nueva", True   # "Permiso de edificación" a secas: se asume obra nueva y se marca como inferido
    return "otros", False


def normalizar_destino(d):
    t = sin_tildes(d)
    if not t:
        return "Sin información"
    if re.search(r"vivienda|habitacional|casa|departamento|condominio", t):
        return "Vivienda"
    if re.search(r"comerc|local|oficina|servicio|hotel|restaurant|hosped|estacion", t):
        return "Comercio y servicios"
    if re.search(r"industri|productiv|bodega|taller|almacen|galpon|agroindustr|agricola|frigorific", t):
        return "Industria y bodegas"
    if re.search(r"equipamiento|educaci|salud|culto|deport|social|cultural|seguridad|esparcimiento|iglesia|colegio|escuela|jardin|clinica|hospital", t):
        return "Equipamiento"
    return "Otro"


MARCAS_EMPRESA = re.compile(
    r"\b(spa|s\.a|sa|ltda|limitada|eirl|e\.i\.r\.l|inmobiliaria|constructora|sociedad|fundacion|corporacion|"
    r"municipalidad|serviu|servicio|ministerio|gobierno|universidad|club|iglesia|junta|comite|cooperativa|"
    r"asociacion|compania|cia|holding|agricola|forestal|empresa|administradora|inversiones|desarrollo|bomberos|cuerpo|ilustre|gobierno regional|hospital|colegio)\b")


def solo_empresas(nombre):
    """Conserva el nombre solo si parece una persona jurídica. Los nombres de personas naturales no se publican."""
    if not nombre:
        return None, None
    return (nombre, "empresa") if MARCAS_EMPRESA.search(sin_tildes(nombre)) else (None, "persona natural")


# ---------- geocodificación ----------
def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def geocodificar(direccion, comuna, cache):
    """Consulta Nominatim (OpenStreetMap), 1 consulta por segundo, con caché en disco. Devuelve (lat, lon) o None."""
    clave = sin_tildes(f"{direccion}|{comuna}")
    if clave in cache:
        return tuple(cache[clave]) if cache[clave] else None
    q = f"{direccion}, {comuna}, Región del Libertador General Bernardo O'Higgins, Chile"
    url = "https://nominatim.openstreetmap.org/search?" + urlencode({"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "cl"})
    try:
        with urlopen(Request(url, headers={"User-Agent": "cchc-ohiggins-permisos/1.0"}), timeout=20) as r:
            res = json.load(r)
        time.sleep(1.1)
    except Exception as e:
        print(f"  (sin geocodificar '{direccion}': {e})")
        return None                       # fallo de red: no se guarda en caché para reintentar después
    cache[clave] = [float(res[0]["lat"]), float(res[0]["lon"])] if res else None
    return tuple(cache[clave]) if cache[clave] else None


# ---------- construcción ----------
def con_pagina(url, pagina):
    if url and pagina and url.lower().split("?")[0].endswith(".pdf"):
        return f"{url}#page={pagina}"
    return url


def publicacion():
    """Resume qué meses tiene publicados cada comuna en el Portal (desde data/manifiesto.json).
    Alimenta la matriz de cobertura del panel. Si aún no hay manifiesto, deja el archivo como está."""
    man = RAIZ / "data" / "manifiesto.json"
    if not man.exists():
        return
    filas = json.loads(man.read_text(encoding="utf-8"))
    notas_f = RAIZ / "data" / "notas_publicacion.json"
    notas = json.loads(notas_f.read_text(encoding="utf-8")) if notas_f.exists() else {}
    slugs = [c["slug"] for c in json.loads((RAIZ / "data" / "comunas.json").read_text(encoding="utf-8"))["comunas"]]
    com = {s: {"meses": {}, "nota": notas.get(s)} for s in slugs}
    for f in filas:
        if f.get("ym") and f["slug"] in com and f["ym"] >= "2026-01" and f.get("url"):
            com[f["slug"]]["meses"][f["ym"]] = com[f["slug"]]["meses"].get(f["ym"], 0) + 1
    todos = sorted({m for c in com.values() for m in c["meses"]})
    (RAIZ / "data" / "publicacion.json").write_text(json.dumps({
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": "Portal de Transparencia (CPLT)",
        "desde": "2026-01", "hasta": todos[-1] if todos else "2026-01", "comunas": com},
        ensure_ascii=False, indent=1), encoding="utf-8")


def mes_sig(ym, d):
    a, m = int(ym[:4]), int(ym[5:])
    t = a * 12 + (m - 1) + d
    return f"{t // 12}-{t % 12 + 1:02d}"


# El Portal rotula mal los meses de algunas comunas (Chépica: el rótulo va un mes adelante del mes real)
DESFASE_PORTAL = {"chepica": -1}


def estados(comunas, por_doc):
    """Para cada mes de 2026 y cada comuna: ¿hay información?, y si no, por qué.
    Estados: con (permisos leídos) · cero (el municipio declara 0) · fallo (publicado, pero no se pudo leer)
    · pendiente (publicado, lectura en curso) · no_publicado."""
    pub_f = RAIZ / "data" / "publicacion.json"
    notas_f = RAIZ / "data" / "cobertura_notas.json"
    if not pub_f.exists():
        return {}
    pub = json.loads(pub_f.read_text(encoding="utf-8"))["comunas"]
    notas = json.loads(notas_f.read_text(encoding="utf-8")) if notas_f.exists() else {}
    publicados = {}
    for slug, x in pub.items():
        d = DESFASE_PORTAL.get(slug, 0)
        publicados[slug] = {mes_sig(m, d) for m in x.get("meses", {})}
    reales = [m for s in publicados.values() for m in s if m >= "2026-01"] + [m for (_, m) in por_doc]
    if not reales:
        return {}
    ult = max(reales)
    out, m = {}, "2026-01"
    while m <= ult:
        out[m] = {}
        for slug, c in comunas.items():
            if (slug, m) in por_doc:
                n, err = por_doc[(slug, m)]
                tardio = any("publicación tardía" in e for e in err)
                if n and tardio:
                    out[m][c["nombre"]] = {"e": "parcial", "t": "Solo se conocen recepciones publicadas tarde en otro listado; falta el listado oficial del mes."}
                elif n:
                    out[m][c["nombre"]] = {"e": "con", "n": n}
                else:
                    t = next((e for e in err if "declara" in e.lower()), None)
                    out[m][c["nombre"]] = {"e": "cero", "t": t or "El municipio informa que no otorgó permisos este mes."} if t else {"e": "fallo", "t": "El documento publicado no trae permisos legibles."}
                continue
            if slug in notas.get("fallo_todos", {}):
                out[m][c["nombre"]] = {"e": "fallo", "t": notas["fallo_todos"][slug]}
            elif m in publicados.get(slug, set()):
                nf = notas.get("fallo", {}).get(slug, {})
                t = nf.get(m) or nf.get("*")
                out[m][c["nombre"]] = {"e": "fallo", "t": t} if t else {"e": "pendiente", "t": "Documento publicado en el Portal; lectura en curso."}
            else:
                out[m][c["nombre"]] = {"e": "no_publicado", "t": notas.get("no_publicado", {}).get(slug, "Sin documento publicado en el Portal para este mes.")}
        m = mes_sig(m, 1)
    return out


def main():
    publicacion()
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-geocodificar", action="store_true")
    a = ap.parse_args()

    comunas = {c["slug"]: c for c in json.loads((RAIZ / "data" / "comunas.json").read_text())["comunas"]}
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    permisos, cobertura, alertas, por_doc = [], {}, [], {}

    for f in sorted(CRUDO.glob("*.json")):
        doc = json.loads(f.read_text())
        c = comunas.get(doc["slug"])
        if not c:
            continue
        cobertura.setdefault(c["nombre"], []).append(doc["mes"])
        por_doc[(doc["slug"], doc["mes"])] = (len(doc["registros"]), doc.get("errores") or [])
        if doc.get("errores"):
            alertas.append(f"{c['nombre']} {doc['mes']}: " + " | ".join(doc["errores"]))
        if not doc["registros"]:
            alertas.append(f"{c['nombre']} {doc['mes']}: sin registros (revisar si el PDF es el correcto)")
        desfasados = [r for r in doc["registros"] if r.get("fecha") and str(r["fecha"])[:7] != doc["mes"]]
        if doc["registros"] and len(desfasados) > 0.2 * len(doc["registros"]):
            alertas.append(f"{c['nombre']} {doc['mes']}: {len(desfasados)} de {len(doc['registros'])} permisos tienen fecha de otro mes "
                           f"(revisar que el archivo esté en el mes correcto)")
        for r in doc["registros"]:
            cat, inferida = clasificar(r.get("tipo_original"))
            prop, prop_tipo = solo_empresas(r.get("propietario"))
            constructora, _ = solo_empresas(r.get("constructora"))
            lat = lon = None
            precision = "comuna"
            if r.get("direccion") and not a.sin_geocodificar:
                g = geocodificar(r["direccion"], c["nombre"], cache)
                if g and km(g[0], g[1], c["lat"], c["lon"]) <= RADIO_MAX_KM:
                    lat, lon, precision = g[0], g[1], "direccion"
            if lat is None:
                lat, lon = c["lat"], c["lon"]
            clave = "|".join(str(r.get(k)) for k in ("numero", "tipo_original", "direccion", "rol"))
            permisos.append({
                "id": f"{doc['slug']}-{doc['mes']}-" + hashlib.sha1(clave.encode()).hexdigest()[:8],
                "comuna": c["nombre"], "slug": doc["slug"], "mes": doc["mes"],
                "fecha": r.get("fecha"), "numero": r.get("numero"),
                "tipo_original": r.get("tipo_original"), "categoria": cat, "categoria_inferida": inferida,
                "destino": normalizar_destino(r.get("destino")), "destino_original": r.get("destino"),
                "proyecto": r.get("proyecto"), "descripcion": r.get("descripcion"),
                "direccion": r.get("direccion"), "rol": r.get("rol"),
                "superficie_m2": r.get("superficie_m2"), "superficie_terreno_m2": r.get("superficie_terreno_m2"),
                "viviendas": r.get("viviendas"), "pisos": r.get("pisos"), "presupuesto": r.get("presupuesto"),
                "propietario": prop, "propietario_tipo": prop_tipo, "constructora": constructora,
                "lat": lat, "lon": lon, "precision": precision,
                "documento_url": con_pagina(doc.get("documento_url"), r.get("pagina")), "pagina": r.get("pagina"),
            })

    vistos, unicos = set(), []
    for p in permisos:                     # elimina duplicados exactos (mismo id)
        if p["id"] not in vistos:
            vistos.add(p["id"])
            unicos.append(p)

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
    for k in cobertura:
        cobertura[k] = sorted(set(cobertura[k]))
    SALIDA.write_text(json.dumps({
        "meta": {"demo": False, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "total": len(unicos), "cobertura": cobertura, "estado": estados(comunas, por_doc), "alertas": alertas},
        "permisos": unicos,
    }, ensure_ascii=False, indent=1))
    print(f"{len(unicos)} permisos en {len(cobertura)} comunas → {SALIDA.relative_to(RAIZ)}")
    for al in alertas:
        print("  ⚠", al)


if __name__ == "__main__":
    main()
