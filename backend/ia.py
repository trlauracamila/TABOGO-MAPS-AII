"""Acceso al modelo de IA (Gemini, multimodal) con salida estructurada."""
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


class ErrorIA(Exception):
    """Falla controlada del modelo de IA (con mensaje entendible)."""


def modelo() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"


def clave_configurada() -> bool:
    k = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(k) and not k.startswith("TU_CLAVE")


_cliente = None
_clave_cliente = None

def cliente():
    global _cliente, _clave_cliente
    if not clave_configurada():
        raise ErrorIA("Falta GEMINI_API_KEY en backend/.env (copia .env.example a .env y pega tu clave).")
    clave = os.getenv("GEMINI_API_KEY").strip()
    if _cliente is None or _clave_cliente != clave:
        _cliente = genai.Client(api_key=clave)
        _clave_cliente = clave
    return _cliente


def traducir_error(e: Exception) -> str:
    t = str(e)
    if "429" in t or "RESOURCE_EXHAUSTED" in t:
        return "Se alcanzó el límite de la API de Gemini (cuota gratuita). Espera un minuto e intenta de nuevo."
    if "API key not valid" in t or "API_KEY_INVALID" in t or "PERMISSION_DENIED" in t or "403" in t:
        return "La clave de Gemini es inválida o no tiene permiso. Revisa GEMINI_API_KEY."
    if "404" in t or "NOT_FOUND" in t:
        return f"El modelo '{modelo()}' no está disponible. Cambia GEMINI_MODEL en .env por otro modelo vigente."
    if "503" in t or "UNAVAILABLE" in t:
        return "El modelo de Gemini está saturado en este momento. Intenta de nuevo en unos segundos."
    return f"Error al consultar Gemini: {t[:300]}"


def generar_estructurado(prompt: str, esquema, imagen_bytes: bytes | None = None, mime_type: str = "image/jpeg"):
    """Llama a Gemini y devuelve una instancia validada del esquema Pydantic indicado."""
    contenido = []
    if imagen_bytes:
        contenido.append(types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type))
    contenido.append(prompt)
    try:
        resp = cliente().models.generate_content(
            model=modelo(),
            contents=contenido,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=esquema, temperature=0.2),
        )
    except ErrorIA:
        raise
    except Exception as e:  # noqa: BLE001
        raise ErrorIA(traducir_error(e)) from e
    try:
        return esquema.model_validate_json(resp.text)
    except Exception as e:  # noqa: BLE001
        raise ErrorIA("La IA devolvió una respuesta que no cumple el formato esperado. Intenta de nuevo.") from e
