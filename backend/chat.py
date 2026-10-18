"""Chat contextual: Gemini con herramientas (function calling) y contexto del caso."""
import json

from google.genai import types

import database
import herramientas as H
import ia

SISTEMA = """Eres el asistente del caso de movilidad {caso_id}. Respondes preguntas posteriores al análisis.

CONTEXTO DEL CASO (datos reales guardados):
{contexto}

REGLAS:
- Responde en español, breve y claro.
- Usa SOLO el contexto del caso y los resultados de tus herramientas. Si no tienes un dato, dilo y, si aplica,
  usa una herramienta para consultarlo.
- No presentes como hechos las "hipotesis" del análisis. Si la verificación fue "parcial", menciónalo.
- Para lugares cercanos, distancias o rutas usa las herramientas; no estimes de memoria.
- Para consultar datos propios de la app usa consultar_servicios_propios.
- Crea una geocerca (crear_geocerca) SOLO si el usuario lo pide de forma explícita.
- Si una herramienta devuelve error, explícalo al usuario sin inventar resultados.
"""


def _contexto(caso: dict, ubicacion: dict | None) -> str:
    geo = caso.get("geo") or {}
    ruta = geo.get("ruta")
    ctx = {
        "solicitud": caso["descripcion"], "estado": caso["estado"], "analisis": caso.get("analisis"),
        "destino": geo.get("destino"), "verificacion": geo.get("verificacion"),
        "candidatos": geo.get("candidatos"), "notas": geo.get("notas"),
        "direccion_usuario_al_crear_el_caso": geo.get("direccion_usuario"),
        "ruta": ({"distancia_m": ruta["distancia_m"], "duracion_s": ruta["duracion_s"], "modo": ruta["modo"],
                  "pasos": ruta["pasos"][:10]} if ruta else None),
        "recomendacion": caso.get("recomendacion"), "acciones": caso.get("acciones"),
        "ubicacion_actual_del_usuario": ubicacion,
    }
    return json.dumps(ctx, ensure_ascii=False, indent=1)


def crear_herramientas(caso: dict, ubicacion: dict | None, registro: list) -> list:
    """Herramientas que el modelo puede invocar durante el chat. Cada llamada queda registrada."""
    caso_id = caso["id"]

    def _err(msg):
        return {"error": msg}

    def consultar_servicios_propios(categoria: str = "", texto: str = "", radio_m: int = 5000) -> dict:
        """Consulta los datos propios de la app (servicios y lugares guardados). categoria puede ser:
        combustible, carga_electrica, parqueadero, transporte_publico, salud, seguridad, turismo, educacion o vacío."""
        r = H.registrar_uso(registro, "consultar_servicios_propios",
                            {"categoria": categoria, "texto": texto, "radio_m": radio_m},
                            lambda: H.consultar_servicios_propios(
                                categoria=categoria or None, texto=texto or None,
                                lat=ubicacion["lat"] if ubicacion else None,
                                lon=ubicacion["lon"] if ubicacion else None, radio_m=radio_m, limite=8))
        return {"resultados": r} if r is not None else _err("No se pudo consultar los datos propios.")

    def buscar_lugares_cercanos(categoria: str, radio_m: int = 2000) -> dict:
        """Busca lugares reales (servicio de mapas) cerca de la ubicación del usuario. categoria: combustible,
        carga_electrica, parqueadero, transporte_publico, salud, farmacia, seguridad, alimentacion, supermercado,
        turismo, educacion o alojamiento."""
        if not ubicacion:
            return _err("No hay ubicación del usuario. Pídele activar el GPS o marcar su posición en el mapa.")
        r = H.registrar_uso(registro, "buscar_lugares_cercanos", {"categoria": categoria, "radio_m": radio_m},
                            lambda: H.buscar_lugares_cercanos(categoria, ubicacion["lat"], ubicacion["lon"], radio_m, 6))
        return {"resultados": r} if r is not None else _err("El servicio de mapas no devolvió resultados o falló.")

    def geocodificar(texto: str) -> dict:
        """Convierte un nombre de lugar o dirección en coordenadas reales usando el servicio de mapas."""
        r = H.registrar_uso(registro, "geocodificar", {"texto": texto},
                            lambda: H.geocodificar(texto, ubicacion["lat"] if ubicacion else None,
                                                   ubicacion["lon"] if ubicacion else None, 3))
        return {"resultados": r} if r is not None else _err("El servicio de mapas falló.")

    def calcular_ruta(destino_lat: float, destino_lon: float, modo: str = "drive") -> dict:
        """Calcula distancia, tiempo y pasos desde la ubicación del usuario hasta un destino. modo: drive, walk o bicycle."""
        if not ubicacion:
            return _err("No hay ubicación del usuario para calcular la ruta.")
        r = H.registrar_uso(registro, "calcular_ruta", {"destino": [destino_lat, destino_lon], "modo": modo},
                            lambda: H.calcular_ruta(ubicacion["lat"], ubicacion["lon"], destino_lat, destino_lon, modo))
        if r is None:
            return _err("No se pudo calcular la ruta.")
        return {"distancia_m": r["distancia_m"], "duracion_s": r["duracion_s"], "modo": r["modo"], "pasos": r["pasos"][:8]}

    def crear_geocerca(nombre: str, lat: float, lon: float, radio_m: int = 150) -> dict:
        """ACCIÓN: crea y guarda una geocerca circular (nombre, centro lat/lon y radio en metros). Úsala solo si el
        usuario lo pidió explícitamente."""
        r = H.registrar_uso(registro, "crear_geocerca", {"nombre": nombre, "lat": lat, "lon": lon, "radio_m": radio_m},
                            lambda: H.crear_geocerca(nombre, lat, lon, radio_m, origen="chat", caso_id=caso_id))
        return r if r is not None else _err("No se pudo crear la geocerca.")

    return [consultar_servicios_propios, buscar_lugares_cercanos, geocodificar, calcular_ruta, crear_geocerca]


def _llamar_modelo(sistema: str, historial: list[dict], mensaje: str, herramientas: list) -> str:
    contenidos = [types.Content(role="user" if m["rol"] == "user" else "model", parts=[types.Part(text=m["contenido"])])
                  for m in historial[-12:]]
    contenidos.append(types.Content(role="user", parts=[types.Part(text=mensaje)]))
    try:
        resp = ia.cliente().models.generate_content(
            model=ia.modelo(), contents=contenidos,
            config=types.GenerateContentConfig(system_instruction=sistema, tools=herramientas, temperature=0.3))
    except ia.ErrorIA:
        raise
    except Exception as e:  # noqa: BLE001
        raise ia.ErrorIA(ia.traducir_error(e)) from e
    return resp.text or ""


def responder(caso_id: str, mensaje: str, lat: float | None = None, lon: float | None = None) -> dict:
    caso = database.obtener_caso(caso_id)
    if not caso:
        raise LookupError(caso_id)
    ubicacion = {"lat": lat, "lon": lon} if lat is not None and lon is not None else caso.get("ubicacion")
    historial = database.listar_mensajes(caso_id)
    registro: list = []
    herramientas = crear_herramientas(caso, ubicacion, registro)
    sistema = SISTEMA.format(caso_id=caso_id, contexto=_contexto(caso, ubicacion))
    texto = _llamar_modelo(sistema, historial, mensaje, herramientas).strip()
    if not texto:
        texto = "No pude generar una respuesta. ¿Puedes reformular la pregunta?"
    database.guardar_mensaje(caso_id, "user", mensaje)
    database.guardar_mensaje(caso_id, "assistant", texto, registro)
    return {"respuesta": texto, "herramientas": registro,
            "geocerca_creada": any(r["nombre"] == "crear_geocerca" and r["ok"] for r in registro)}
