"""API de UrbanMobility AI (FastAPI).

Ejecutar:  uvicorn main:app --reload
"""
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

import agentes  # noqa: E402
import chat  # noqa: E402
import database  # noqa: E402
import herramientas as H  # noqa: E402
import ia  # noqa: E402
from esquemas import ChatIn, EventoGeocercaIn, GeocercaIn  # noqa: E402
from imagenes import preparar_imagen  # noqa: E402

database.init_db()
ORQUESTADOR = agentes.crear_orquestador()

app = FastAPI(title="TABOGO MAPS IA", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_IMAGEN_BYTES = 15 * 1024 * 1024
FRASE_FOTO = "Identifica el lugar de esta foto e indícame su dirección."


@app.get("/api/salud")
def salud():
    return {"ok": True, "gemini_configurado": ia.clave_configurada(), "modelo_ia": ia.modelo(),
            "proveedor_mapas": H.proveedor_mapas(), "categorias": list(H.CATEGORIAS)}


# ------------------------------------------------------------ análisis del caso
@app.post("/api/analizar-caso")
def analizar_caso(
    descripcion: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    precision: float | None = Form(None),
    imagen: UploadFile | None = File(None),
):
    imagen_bytes, mime, exif, nombre = None, "image/jpeg", None, None
    if imagen is not None and imagen.filename:
        datos = imagen.file.read()
        if len(datos) > MAX_IMAGEN_BYTES:
            raise HTTPException(413, "La imagen supera 15 MB.")
        if not (imagen.content_type or "").startswith("image/"):
            raise HTTPException(400, "El archivo adjunto debe ser una imagen.")
        imagen_bytes, mime, exif = preparar_imagen(datos, imagen.content_type)
        nombre = imagen.filename

    descripcion = descripcion.strip()
    if not descripcion and imagen_bytes:
        descripcion = FRASE_FOTO
    if not descripcion:
        raise HTTPException(400, "Escribe una descripción o adjunta una foto.")

    ubicacion = None
    if lat is not None and lon is not None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(400, "Coordenadas fuera de rango.")
        ubicacion = {"lat": lat, "lon": lon, "precision": precision}

    estado = {
        "caso_id": f"CASO-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}",
        "creado_en": database.ahora(), "descripcion": descripcion, "ubicacion": ubicacion, "exif_gps": exif,
        "imagen_bytes": imagen_bytes, "mime_type": mime, "imagen_nombre": nombre, "traza": [],
    }
    try:
        resultado = ORQUESTADOR.invoke(estado)
    except ia.ErrorIA as e:
        raise HTTPException(502, str(e)) from e
    return resultado["caso_final"]


@app.get("/api/casos")
def listar_casos():
    return database.listar_casos()


@app.get("/api/casos/{caso_id}")
def obtener_caso(caso_id: str):
    caso = database.obtener_caso(caso_id)
    if not caso:
        raise HTTPException(404, "Caso no encontrado")
    return caso


# ------------------------------------------------------------------- chat
@app.post("/api/casos/{caso_id}/chat")
def chat_caso(caso_id: str, cuerpo: ChatIn):
    if not cuerpo.mensaje.strip():
        raise HTTPException(400, "Escribe un mensaje.")
    try:
        return chat.responder(caso_id, cuerpo.mensaje.strip(), cuerpo.lat, cuerpo.lon)
    except LookupError:
        raise HTTPException(404, "Caso no encontrado")
    except ia.ErrorIA as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/casos/{caso_id}/mensajes")
def mensajes_caso(caso_id: str):
    if not database.obtener_caso(caso_id):
        raise HTTPException(404, "Caso no encontrado")
    return database.listar_mensajes(caso_id)


# -------------------------------------------------- datos propios y mapas
@app.get("/api/servicios")
def servicios(categoria: str | None = None):
    return database.listar_servicios(categoria)


@app.get("/api/geo/buscar")
def geo_buscar(q: str, lat: float | None = None, lon: float | None = None):
    try:
        return H.geocodificar(q, lat, lon, 5)
    except H.ServicioExternoError as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/geo/inversa")
def geo_inversa(lat: float, lon: float):
    try:
        return H.geocodificar_inverso(lat, lon)
    except H.ServicioExternoError as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/geo/ruta")
def geo_ruta(origen_lat: float, origen_lon: float, destino_lat: float, destino_lon: float, modo: str = "drive"):
    try:
        return H.calcular_ruta(origen_lat, origen_lon, destino_lat, destino_lon, modo)
    except H.ServicioExternoError as e:
        raise HTTPException(502, str(e)) from e


# --------------------------------------------------------------- geocercas
@app.get("/api/geocercas")
def listar_geocercas():
    return database.listar_geocercas()


@app.post("/api/geocercas")
def crear_geocerca(g: GeocercaIn):
    try:
        return H.crear_geocerca(g.nombre, g.lat, g.lon, g.radio_m, origen="manual")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/geocercas/{geocerca_id}")
def eliminar_geocerca(geocerca_id: int):
    if not database.eliminar_geocerca(geocerca_id):
        raise HTTPException(404, "Geocerca no encontrada")
    return {"eliminada": geocerca_id}


@app.post("/api/geocercas/{geocerca_id}/eventos")
def evento_geocerca(geocerca_id: int, ev: EventoGeocercaIn):
    if ev.tipo not in ("entrada", "salida"):
        raise HTTPException(400, "tipo debe ser 'entrada' o 'salida'")
    r = database.registrar_evento_geocerca(geocerca_id, ev.tipo, ev.lat, ev.lon)
    if r is None:
        raise HTTPException(404, "Geocerca no encontrada")
    return r


@app.get("/api/eventos-geocerca")
def eventos_geocerca():
    return database.listar_eventos_geocerca()
