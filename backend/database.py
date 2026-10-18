"""Persistencia (SQLite) y datos propios de la aplicación.

Tablas:
  servicios         -> datos propios (lugares/servicios urbanos, editables en datos/servicios_seed.json)
  casos             -> cada caso procesado: análisis IA, resultado geográfico, recomendación, acciones y traza
  mensajes          -> historial del chat contextual de cada caso
  geocercas         -> zonas circulares (creadas por el usuario, por la IA o por el chat)
  eventos_geocerca  -> entradas/salidas detectadas por el GPS del navegador
"""
import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
_db_env = Path(os.getenv("DB_PATH", "movilidad.db"))
DB_PATH = _db_env if _db_env.is_absolute() else BASE_DIR / _db_env
SEED_PATH = BASE_DIR / "datos" / "servicios_seed.json"


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distancia en metros entre dos coordenadas."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@contextmanager
def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with conectar() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS servicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                descripcion TEXT,
                direccion TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                horario TEXT
            );
            CREATE TABLE IF NOT EXISTS casos (
                id TEXT PRIMARY KEY,
                creado_en TEXT NOT NULL,
                descripcion TEXT,
                lat_usuario REAL,
                lon_usuario REAL,
                imagen_nombre TEXT,
                estado TEXT NOT NULL,
                analisis TEXT,
                geo TEXT,
                recomendacion TEXT,
                acciones TEXT,
                traza TEXT
            );
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caso_id TEXT NOT NULL,
                rol TEXT NOT NULL,
                contenido TEXT NOT NULL,
                herramientas TEXT,
                creado_en TEXT NOT NULL,
                FOREIGN KEY (caso_id) REFERENCES casos(id)
            );
            CREATE TABLE IF NOT EXISTS geocercas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                radio_m REAL NOT NULL,
                origen TEXT NOT NULL DEFAULT 'manual',
                caso_id TEXT,
                creado_en TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS eventos_geocerca (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                geocerca_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                lat REAL,
                lon REAL,
                creado_en TEXT NOT NULL,
                FOREIGN KEY (geocerca_id) REFERENCES geocercas(id) ON DELETE CASCADE
            );
            """
        )
        total = c.execute("SELECT COUNT(*) FROM servicios").fetchone()[0]
        if total == 0 and SEED_PATH.exists():
            for s in json.loads(SEED_PATH.read_text(encoding="utf-8")):
                c.execute(
                    "INSERT INTO servicios (nombre, categoria, descripcion, direccion, lat, lon, horario) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (s["nombre"], s["categoria"], s.get("descripcion"), s.get("direccion"),
                     s["lat"], s["lon"], s.get("horario")),
                )


# ---------------------------------------------------------------- datos propios
def listar_servicios(categoria: str | None = None) -> list[dict]:
    with conectar() as c:
        if categoria:
            filas = c.execute("SELECT * FROM servicios WHERE categoria = ? ORDER BY nombre", (categoria,)).fetchall()
        else:
            filas = c.execute("SELECT * FROM servicios ORDER BY nombre").fetchall()
    return [dict(f) for f in filas]


def servicios_cercanos(lat=None, lon=None, radio_m=5000, categoria=None, texto=None, limite=8) -> list[dict]:
    """Consulta los datos propios filtrando por categoría, texto y cercanía."""
    items = listar_servicios(categoria)
    if texto:
        t = texto.lower()
        items = [s for s in items if t in (s["nombre"] or "").lower() or t in (s["descripcion"] or "").lower()]
    if lat is not None and lon is not None:
        for s in items:
            s["distancia_m"] = round(haversine_m(lat, lon, s["lat"], s["lon"]))
        items = [s for s in items if s["distancia_m"] <= radio_m]
        items.sort(key=lambda s: s["distancia_m"])
    for s in items:
        s["fuente"] = "datos_propios"
    return items[:limite]


# ---------------------------------------------------------------------- casos
def guardar_caso(caso: dict) -> None:
    ub = caso.get("ubicacion") or {}
    with conectar() as c:
        c.execute(
            "INSERT OR REPLACE INTO casos (id, creado_en, descripcion, lat_usuario, lon_usuario, imagen_nombre, "
            "estado, analisis, geo, recomendacion, acciones, traza) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                caso["id"], caso["creado_en"], caso.get("descripcion"), ub.get("lat"), ub.get("lon"),
                caso.get("imagen_nombre"), caso["estado"],
                json.dumps(caso.get("analisis"), ensure_ascii=False),
                json.dumps(caso.get("geo"), ensure_ascii=False),
                json.dumps(caso.get("recomendacion"), ensure_ascii=False),
                json.dumps(caso.get("acciones"), ensure_ascii=False),
                json.dumps(caso.get("traza"), ensure_ascii=False),
            ),
        )


def _fila_a_caso(f: sqlite3.Row) -> dict:
    ub = None
    if f["lat_usuario"] is not None and f["lon_usuario"] is not None:
        ub = {"lat": f["lat_usuario"], "lon": f["lon_usuario"]}
    return {
        "id": f["id"], "creado_en": f["creado_en"], "descripcion": f["descripcion"], "ubicacion": ub,
        "imagen_nombre": f["imagen_nombre"], "estado": f["estado"],
        "analisis": json.loads(f["analisis"] or "null"), "geo": json.loads(f["geo"] or "null"),
        "recomendacion": json.loads(f["recomendacion"] or "null"),
        "acciones": json.loads(f["acciones"] or "[]"), "traza": json.loads(f["traza"] or "[]"),
    }


def obtener_caso(caso_id: str) -> dict | None:
    with conectar() as c:
        f = c.execute("SELECT * FROM casos WHERE id = ?", (caso_id,)).fetchone()
    return _fila_a_caso(f) if f else None


def listar_casos(limite: int = 50) -> list[dict]:
    """Resumen liviano (sin geometría de rutas) para el historial."""
    with conectar() as c:
        filas = c.execute("SELECT * FROM casos ORDER BY creado_en DESC, id DESC LIMIT ?", (limite,)).fetchall()
    res = []
    for f in filas:
        caso = _fila_a_caso(f)
        destino = (caso["geo"] or {}).get("destino")
        res.append({
            "id": caso["id"], "creado_en": caso["creado_en"], "descripcion": caso["descripcion"],
            "estado": caso["estado"], "imagen_nombre": caso["imagen_nombre"],
            "destino": destino["nombre"] if destino else None,
            "agentes": [t["agente"] for t in caso["traza"]],
            "acciones": [a["tipo"] for a in caso["acciones"] if a.get("estado") == "ejecutada"],
        })
    return res


# --------------------------------------------------------------------- chat
def guardar_mensaje(caso_id: str, rol: str, contenido: str, herramientas: list | None = None) -> None:
    with conectar() as c:
        c.execute(
            "INSERT INTO mensajes (caso_id, rol, contenido, herramientas, creado_en) VALUES (?,?,?,?,?)",
            (caso_id, rol, contenido, json.dumps(herramientas or [], ensure_ascii=False), ahora()),
        )


def listar_mensajes(caso_id: str) -> list[dict]:
    with conectar() as c:
        filas = c.execute("SELECT * FROM mensajes WHERE caso_id = ? ORDER BY id", (caso_id,)).fetchall()
    return [{"rol": f["rol"], "contenido": f["contenido"],
             "herramientas": json.loads(f["herramientas"] or "[]"), "creado_en": f["creado_en"]} for f in filas]


# ---------------------------------------------------------------- geocercas
def crear_geocerca_db(nombre: str, lat: float, lon: float, radio_m: float, origen="manual", caso_id=None) -> dict:
    with conectar() as c:
        cur = c.execute(
            "INSERT INTO geocercas (nombre, lat, lon, radio_m, origen, caso_id, creado_en) VALUES (?,?,?,?,?,?,?)",
            (nombre, lat, lon, radio_m, origen, caso_id, ahora()),
        )
        fila = c.execute("SELECT * FROM geocercas WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(fila)


def listar_geocercas() -> list[dict]:
    with conectar() as c:
        return [dict(f) for f in c.execute("SELECT * FROM geocercas ORDER BY id DESC").fetchall()]


def eliminar_geocerca(geocerca_id: int) -> bool:
    with conectar() as c:
        cur = c.execute("DELETE FROM geocercas WHERE id = ?", (geocerca_id,))
        return cur.rowcount > 0


def registrar_evento_geocerca(geocerca_id: int, tipo: str, lat=None, lon=None) -> dict | None:
    with conectar() as c:
        if not c.execute("SELECT 1 FROM geocercas WHERE id = ?", (geocerca_id,)).fetchone():
            return None
        cur = c.execute(
            "INSERT INTO eventos_geocerca (geocerca_id, tipo, lat, lon, creado_en) VALUES (?,?,?,?,?)",
            (geocerca_id, tipo, lat, lon, ahora()),
        )
        return dict(c.execute("SELECT * FROM eventos_geocerca WHERE id = ?", (cur.lastrowid,)).fetchone())


def listar_eventos_geocerca(limite: int = 50) -> list[dict]:
    with conectar() as c:
        filas = c.execute(
            "SELECT e.*, g.nombre AS geocerca FROM eventos_geocerca e "
            "JOIN geocercas g ON g.id = e.geocerca_id ORDER BY e.id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(f) for f in filas]
