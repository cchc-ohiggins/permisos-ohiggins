"""Genera data/demo.json: registros FICTICIOS para probar el diseño del panel.
Sigue los meses que cada comuna realmente tiene publicados (data/publicacion.json).
Nada de esto es información real; el panel lo marca con una franja de aviso."""
import json, random, hashlib
from pathlib import Path
from datetime import datetime, timezone

R = Path(__file__).resolve().parent.parent
random.seed(2026)
com = json.loads((R / "data/comunas.json").read_text(encoding="utf-8"))["comunas"]
pub = json.loads((R / "data/publicacion.json").read_text(encoding="utf-8"))["comunas"]
PESO = {"rancagua": 26, "machali": 15, "san-fernando": 10, "rengo": 9, "santa-cruz": 6, "pichilemu": 6, "graneros": 5, "mostazal": 5,
        "requinoa": 5, "chimbarongo": 4, "codegua": 4, "donihue": 4, "malloa": 3, "las-cabras": 3, "peumo": 3, "nancagua": 3,
        "pichidegua": 3, "coltauco": 3, "quinta-de-tilcoco": 3, "chepica": 3, "peralillo": 2, "pumanque": 1, "paredones": 2,
        "la-estrella": 1, "marchihue": 2, "navidad": 3, "coinco": 2}
EMP = ["Inmobiliaria Ejemplo Norte SpA", "Constructora Ejemplo Sur S.A.", "Desarrollo Ejemplo Valle SpA", "Inmobiliaria Ejemplo Cordillera Ltda.",
       "Constructora Demo Centro SpA", "Inmobiliaria Demo Cachapoal SpA", "Agrícola Ejemplo Los Robles S.A.", "Logística Ejemplo Ruta 5 SpA",
       "Inmobiliaria Demo Colchagua SpA", "Constructora Demo Pacífico Ltda.", "Fundación Ejemplo Educa", "Supermercados Ejemplo S.A."]
TIPOS = [("nueva", "Permiso de edificación obra nueva", 30), ("modificacion", "Modificación de proyecto", 9), ("ampliacion", "Permiso de ampliación", 8),
         ("regularizacion", "Regularización de edificación existente (Ley 20.898)", 22), ("obra_menor", "Permiso de obra menor", 12),
         ("recepcion", "Certificado de recepción definitiva", 14), ("subdivision", "Subdivisión / loteo", 5)]
DEST = [("Vivienda", 62), ("Comercio y servicios", 14), ("Industria y bodegas", 9), ("Equipamiento", 9), ("Otros", 6)]
NOMBRES = ["Condominio Los Aromos", "Villa El Sauce", "Loteo Altos del Valle", "Bodega logística", "Centro comercial", "Colegio", "Edificio Plaza", "Conjunto Las Acacias", "Planta de procesos", "Supermercado"]

def pick(lista):
    r = random.uniform(0, sum(x[-1] for x in lista)); a = 0
    for x in lista:
        a += x[-1]
        if r <= a: return x
    return lista[-1]

permisos = []
cobertura = {}
for c in com:
    meses = sorted(pub.get(c["slug"], {}).get("meses", {}))
    if not meses: continue
    cobertura[c["nombre"]] = meses
    for m in meses:
        n = max(1, int(random.gauss(PESO.get(c["slug"], 2), PESO.get(c["slug"], 2) * .3)))
        for i in range(n):
            cat, tipo, _ = pick(TIPOS); dest = pick(DEST)[0]
            sup = viv = None; desc = None
            grande = cat in ("nueva", "ampliacion") and random.random() < .05
            if cat in ("nueva", "ampliacion", "modificacion", "regularizacion", "obra_menor"):
                if dest == "Vivienda":
                    viv = random.choice([1, 1, 1, 2, 4, 6, 12, 24, 40]) if cat != "regularizacion" else 1
                    if grande: viv = random.randint(50, 272)
                    sup = round(viv * random.uniform(55, 95), 1) if cat != "regularizacion" else round(random.uniform(40, 110), 1)
                else:
                    sup = round(random.uniform(120, 1400), 1)
                    if grande: sup = round(random.uniform(1500, 9000), 1)
                desc = "[Ejemplo] " + (f"Construcción de {viv} viviendas" if viv and viv > 1 else "Obra de edificación")
            emp = random.choice(EMP) if cat in ("nueva", "ampliacion") and random.random() < .7 else None
            dia = random.randint(1, 28)
            lat = c["lat"] + random.gauss(0, .02); lon = c["lon"] + random.gauss(0, .025)
            prec = "direccion" if random.random() < .7 else "comuna"
            if prec == "comuna": lat, lon = c["lat"], c["lon"]
            pid = hashlib.md5(f"{c['slug']}{m}{i}".encode()).hexdigest()[:8]
            permisos.append({
                "id": f"{c['slug']}-{m}-{pid}", "comuna": c["nombre"], "slug": c["slug"], "mes": m, "fecha": f"{m}-{dia:02d}",
                "numero": f"{random.randint(1, 400)}", "tipo_original": tipo, "categoria": cat, "categoria_inferida": False,
                "destino": dest, "destino_original": dest, "proyecto": f"[Ejemplo] {random.choice(NOMBRES)} {random.randint(1, 30)}" if emp else None,
                "descripcion": desc, "direccion": f"Calle Ejemplo {random.randint(10, 3000)}", "rol": f"{random.randint(1, 900)}-{random.randint(1, 99)}",
                "superficie_m2": sup, "superficie_terreno_m2": round(sup * random.uniform(1.4, 4), 0) if sup else None, "viviendas": viv,
                "pisos": random.choice([1, 2, 2, 3]) if sup else None, "presupuesto": None, "propietario": emp,
                "propietario_tipo": "empresa" if emp else None, "constructora": None, "lat": round(lat, 5), "lon": round(lon, 5),
                "precision": prec, "documento_url": "https://example.org/documento-de-ejemplo.pdf", "pagina": None})
permisos.sort(key=lambda p: p["fecha"])
(R / "data/demo.json").write_text(json.dumps({"meta": {"demo": True, "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "total": len(permisos), "cobertura": cobertura, "alertas": []}, "permisos": permisos}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(len(permisos), "registros ficticios en", len(cobertura), "comunas")
