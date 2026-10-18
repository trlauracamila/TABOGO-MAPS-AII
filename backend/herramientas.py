"""Herramientas que usan los agentes y el chat.

Consulta de datos propios : consultar_servicios_propios
Servicio externo de mapas : geocodificar, geocodificar_inverso, buscar_lugares_cercanos, calcular_ruta
                            (Geoapify si hay GEOAPIFY_API_KEY; si no, Nominatim/OpenStreetMap + OSRM)
Acción sobre el sistema   : crear_geocerca
"""
import difflib
import os
import re
import threading
import time
import unicodedata

import httpx

import database
from database import haversine_m

GEOAPIFY = "https://api.geoapify.com"
NOMINATIM = "https://nominatim.openstreetmap.org"
OSRM = "https://router.project-osrm.org"
USER_AGENT = "MovilidadIA-UNIMINUTO/1.0 (proyecto academico)"

# categoría amigable -> categoría Geoapify / término para Nominatim
CATEGORIAS = {
    "combustible": {"geoapify": "service.vehicle.fuel", "termino": "estación de servicio gasolina"},
    "carga_electrica": {"geoapify": "service.vehicle.charging_station", "termino": "estación de carga eléctrica"},
    "parqueadero": {"geoapify": "parking", "termino": "parqueadero"},
    "transporte_publico": {"geoapify": "public_transport", "termino": "estación de transporte"},
    "salud": {"geoapify": "healthcare", "termino": "hospital clínica"},
    "farmacia": {"geoapify": "healthcare.pharmacy", "termino": "farmacia"},
    "seguridad": {"geoapify": "service.police", "termino": "estación de policía"},
    "alimentacion": {"geoapify": "catering", "termino": "restaurante"},
    "supermercado": {"geoapify": "commercial.supermarket", "termino": "supermercado"},
    "turismo": {"geoapify": "tourism", "termino": "atracción turística"},
    "educacion": {"geoapify": "education", "termino": "universidad colegio"},
    "alojamiento": {"geoapify": "accommodation", "termino": "hotel"},
}
MODOS = {"drive", "walk", "bicycle"}


class ServicioExternoError(Exception):
    """Falla controlada de un servicio externo (mapas)."""


def proveedor_mapas() -> str:
    return "geoapify" if _key() else "nominatim_osm"


def _key() -> str:
    k = os.getenv("GEOAPIFY_API_KEY", "").strip()
    return "" if (not k or k.startswith("TU_CLAVE")) else k


_nominatim_lock = threading.Lock()
_nominatim_ultimo = 0.0


def _get_json(url: str, params: dict, nominatim: bool = False):
    global _nominatim_ultimo
    headers = {"User-Agent": USER_AGENT}
    if nominatim:  # política de uso de Nominatim: máx. 1 solicitud por segundo
        with _nominatim_lock:
            espera = 1.1 - (time.time() - _nominatim_ultimo)
            if espera > 0:
                time.sleep(espera)
            _nominatim_ultimo = time.time()
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=15.0)
    except httpx.HTTPError as e:
        raise ServicioExternoError(f"No se pudo conectar con el servicio de mapas: {e}") from e
    if r.status_code in (401, 403):
        raise ServicioExternoError("La clave de Geoapify es inválida o no tiene permiso (revisa GEOAPIFY_API_KEY).")
    if r.status_code == 429:
        raise ServicioExternoError("Se alcanzó el límite de uso del servicio de mapas. Intenta más tarde.")
    if r.status_code >= 400:
        raise ServicioExternoError(f"El servicio de mapas respondió con error {r.status_code}.")
    try:
        return r.json()
    except ValueError as e:
        raise ServicioExternoError("El servicio de mapas devolvió una respuesta no válida.") from e


# ----------------------------------------------------------- utilidades
def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def similitud_nombre(a: str, b: str) -> float:
    """0..1: qué tanto se parecen dos nombres de lugar."""
    a, b = _normalizar(a), _normalizar(b)
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta):
        return 0.9
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


def _con_distancia(item: dict, lat, lon) -> dict:
    if lat is not None and lon is not None and item.get("lat") is not None:
        item["distancia_m"] = round(haversine_m(lat, lon, item["lat"], item["lon"]))
    return item


# -------------------------------------------------- datos propios (BD)
def consultar_servicios_propios(categoria=None, texto=None, lat=None, lon=None, radio_m=5000, limite=8) -> list[dict]:
    return database.servicios_cercanos(lat=lat, lon=lon, radio_m=radio_m, categoria=categoria, texto=texto, limite=limite)


# --------------------------------------------- servicio externo de mapas
def geocodificar(texto: str, cerca_lat=None, cerca_lon=None, limite=5) -> list[dict]:
    """Texto (nombre o dirección) -> coordenadas reales."""
    if not texto or not texto.strip():
        return []
    if _key():
        params = {"text": texto, "format": "json", "limit": limite, "lang": "es", "apiKey": _key()}
        if cerca_lat is not None and cerca_lon is not None:
            params["bias"] = f"proximity:{cerca_lon},{cerca_lat}"
        data = _get_json(f"{GEOAPIFY}/v1/geocode/search", params)
        salida = [{
            "nombre": r.get("name") or r.get("address_line1") or texto,
            "direccion": r.get("formatted"), "lat": r["lat"], "lon": r["lon"],
            "categoria": r.get("category"), "fuente": "geoapify",
        } for r in data.get("results", []) if "lat" in r and "lon" in r]
    else:
        params = {"q": texto, "format": "jsonv2", "limit": limite, "accept-language": "es"}
        if cerca_lat is not None and cerca_lon is not None:
            d = 0.25
            params["viewbox"] = f"{cerca_lon - d},{cerca_lat + d},{cerca_lon + d},{cerca_lat - d}"
        data = _get_json(f"{NOMINATIM}/search", params, nominatim=True)
        salida = [{
            "nombre": r.get("name") or r.get("display_name", "").split(",")[0],
            "direccion": r.get("display_name"), "lat": float(r["lat"]), "lon": float(r["lon"]),
            "categoria": r.get("type"), "fuente": "nominatim_osm",
        } for r in data]
    return [_con_distancia(s, cerca_lat, cerca_lon) for s in salida]


def geocodificar_inverso(lat: float, lon: float) -> dict:
    """Coordenadas -> dirección legible."""
    if _key():
        data = _get_json(f"{GEOAPIFY}/v1/geocode/reverse",
                         {"lat": lat, "lon": lon, "format": "json", "lang": "es", "apiKey": _key()})
        res = (data.get("results") or [None])[0]
        if not res:
            return {"direccion": None, "ciudad": None, "barrio": None, "lat": lat, "lon": lon, "fuente": "geoapify"}
        return {"direccion": res.get("formatted"), "ciudad": res.get("city"), "barrio": res.get("suburb"),
                "lat": lat, "lon": lon, "fuente": "geoapify"}
    data = _get_json(f"{NOMINATIM}/reverse",
                     {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "accept-language": "es"}, nominatim=True)
    dir_ = (data or {}).get("address", {})
    return {"direccion": (data or {}).get("display_name"),
            "ciudad": dir_.get("city") or dir_.get("town") or dir_.get("municipality"),
            "barrio": dir_.get("suburb") or dir_.get("neighbourhood"),
            "lat": lat, "lon": lon, "fuente": "nominatim_osm"}


def buscar_lugares_cercanos(categoria: str, lat: float, lon: float, radio_m: int = 2000, limite: int = 8) -> list[dict]:
    """Lugares reales de una categoría cerca de un punto."""
    if categoria not in CATEGORIAS:
        raise ServicioExternoError(f"Categoría no soportada: {categoria}. Usa una de: {', '.join(CATEGORIAS)}")
    radio_m = max(100, min(int(radio_m), 20000))
    if _key():
        data = _get_json(f"{GEOAPIFY}/v2/places", {
            "categories": CATEGORIAS[categoria]["geoapify"],
            "filter": f"circle:{lon},{lat},{radio_m}", "bias": f"proximity:{lon},{lat}",
            "limit": limite, "lang": "es", "apiKey": _key()})
        salida = []
        for f in data.get("features", []):
            p = f.get("properties", {})
            nombre = p.get("name") or p.get("address_line1")
            if not nombre or "lat" not in p:
                continue
            salida.append({"nombre": nombre, "direccion": p.get("formatted"), "lat": p["lat"], "lon": p["lon"],
                           "categoria": categoria, "fuente": "geoapify"})
    else:
        d = radio_m / 111000.0
        data = _get_json(f"{NOMINATIM}/search", {
            "q": CATEGORIAS[categoria]["termino"], "format": "jsonv2", "limit": limite, "accept-language": "es",
            "viewbox": f"{lon - d},{lat + d},{lon + d},{lat - d}", "bounded": 1}, nominatim=True)
        salida = [{"nombre": r.get("name") or r.get("display_name", "").split(",")[0],
                   "direccion": r.get("display_name"), "lat": float(r["lat"]), "lon": float(r["lon"]),
                   "categoria": categoria, "fuente": "nominatim_osm"} for r in data]
    salida = [_con_distancia(s, lat, lon) for s in salida]
    salida.sort(key=lambda s: s.get("distancia_m", 0))
    return salida[:limite]


def _adelgazar(puntos: list[list[float]], maximo: int = 1500) -> list[list[float]]:
    if len(puntos) <= maximo:
        return puntos
    paso = len(puntos) / maximo
    return [puntos[int(i * paso)] for i in range(maximo)] + [puntos[-1]]


def calcular_ruta(origen_lat: float, origen_lon: float, destino_lat: float, destino_lon: float,
                  modo: str = "drive") -> dict:
    """Ruta real origen -> destino (distancia, tiempo, geometría y pasos)."""
    if modo not in MODOS:
        modo = "drive"
    if _key():
        data = _get_json(f"{GEOAPIFY}/v1/routing", {
            "waypoints": f"{origen_lat},{origen_lon}|{destino_lat},{destino_lon}",
            "mode": modo, "lang": "es", "apiKey": _key()})
        feats = data.get("features") or []
        if not feats:
            raise ServicioExternoError("No se encontró una ruta entre los dos puntos.")
        f = feats[0]
        prop = f.get("properties", {})
        geom = f.get("geometry", {})
        lineas = geom.get("coordinates", [])
        if geom.get("type") == "LineString":
            lineas = [lineas]
        puntos = [[p[1], p[0]] for linea in lineas for p in linea]
        pasos = []
        for leg in prop.get("legs", []):
            for st in leg.get("steps", []):
                txt = (st.get("instruction") or {}).get("text")
                if txt:
                    pasos.append(txt)
        return {"distancia_m": round(prop.get("distance", 0)), "duracion_s": round(prop.get("time", 0)),
                "geometria": _adelgazar(puntos), "pasos": pasos, "modo": modo, "fuente": "geoapify"}
    # Respaldo sin clave: OSRM público (solo conducción)
    data = _get_json(f"{OSRM}/route/v1/driving/{origen_lon},{origen_lat};{destino_lon},{destino_lat}",
                     {"overview": "full", "geometries": "geojson", "steps": "true"})
    rutas = data.get("routes") or []
    if not rutas:
        raise ServicioExternoError("No se encontró una ruta entre los dos puntos.")
    r = rutas[0]
    pasos = []
    for leg in r.get("legs", []):
        for st in leg.get("steps", []):
            if st.get("name"):
                pasos.append(f"Continúa por {st['name']} ({round(st.get('distance', 0))} m)")
    return {"distancia_m": round(r["distance"]), "duracion_s": round(r["duration"]),
            "geometria": _adelgazar([[p[1], p[0]] for p in r["geometry"]["coordinates"]]),
            "pasos": pasos, "modo": "drive", "fuente": "osrm_publico"}


# ------------------------------------------------------------- ACCIÓN
def crear_geocerca(nombre: str, lat: float, lon: float, radio_m: float = 150, origen: str = "manual",
                   caso_id: str | None = None) -> dict:
    """Acción real: crea y guarda una geocerca circular en la base de datos."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenadas fuera de rango.")
    radio_m = max(20.0, min(float(radio_m), 5000.0))
    return database.crear_geocerca_db(nombre.strip() or "Geocerca", lat, lon, radio_m, origen, caso_id)


# ------------------------------------------------- registro de uso (trazabilidad)
def _resumen(r) -> str:
    if isinstance(r, list):
        return f"{len(r)} resultado(s)"
    if isinstance(r, dict):
        if "distancia_m" in r and "duracion_s" in r:
            return f"{r['distancia_m']} m, {r['duracion_s']} s"
        if r.get("direccion"):
            return str(r["direccion"])[:90]
        if "id" in r:
            return f"id {r['id']}"
    return "ok"


def registrar_uso(registro: list, nombre: str, entrada: dict, fn):
    """Ejecuta una herramienta y deja constancia (nombre, entrada, éxito, resumen, ms) para la trazabilidad.
    Devuelve el resultado o None si la herramienta falló de forma controlada."""
    t0 = time.perf_counter()
    try:
        r = fn()
        registro.append({"nombre": nombre, "entrada": entrada, "ok": True, "resumen": _resumen(r),
                         "ms": round((time.perf_counter() - t0) * 1000)})
        return r
    except (ServicioExternoError, ValueError) as e:
        registro.append({"nombre": nombre, "entrada": entrada, "ok": False, "resumen": str(e)[:200],
                         "ms": round((time.perf_counter() - t0) * 1000)})
        return None
