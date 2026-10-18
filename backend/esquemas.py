"""Esquemas (respuesta estructurada de la IA y cuerpos de la API)."""
from enum import Enum

from pydantic import BaseModel, Field


class EstadoInformacion(str, Enum):
    suficiente = "suficiente"
    insuficiente = "insuficiente"
    contradictoria = "contradictoria"
    no_corresponde = "no_corresponde"


class TipoSolicitud(str, Enum):
    identificar_lugar = "identificar_lugar"
    buscar_servicio = "buscar_servicio"
    como_llegar = "como_llegar"
    otro = "otro"


class Confianza(str, Enum):
    alta = "alta"
    media = "media"
    baja = "baja"


class ModoTransporte(str, Enum):
    drive = "drive"
    walk = "walk"
    bicycle = "bicycle"


class LugarIdentificado(BaseModel):
    nombre: str = Field(description="Nombre del lugar o negocio. Cadena vacía si no se puede identificar.")
    categoria: str = Field(description="Tipo de lugar (ej. centro comercial, estación de servicio, plaza, universidad).")
    direccion_estimada: str = Field(description="Dirección SOLO si aparece escrita/visible; si no, cadena vacía.")
    ciudad: str = Field(description="Ciudad si se puede inferir con razonable certeza; si no, cadena vacía.")
    pistas_visuales: list[str] = Field(description="Elementos visuales que sustentan la identificación.")
    texto_visible: list[str] = Field(description="Textos legibles en la imagen (letreros, placas, avisos).")
 

class AnalisisIA(BaseModel):
    tipo_solicitud: TipoSolicitud
    resumen_necesidad: str = Field(description="Qué necesita el usuario, en una o dos frases.")
    categoria_servicio: str = Field(description="Una categoría permitida o 'ninguna'.")
    modo_transporte: ModoTransporte
    lugar: LugarIdentificado
    confianza_identificacion: Confianza
    estado_informacion: EstadoInformacion
    motivo_estado: str = Field(description="Por qué la información es suficiente o no.")
    preguntas_aclaratorias: list[str] = Field(description="Máximo 3 preguntas si falta información; si no, lista vacía.")
    hechos_observados: list[str] = Field(description="Lo que se observa directamente en la imagen/texto.")
    hipotesis: list[str] = Field(description="Inferencias NO confirmadas.")


class Recomendacion(BaseModel):
    titulo: str
    resumen: str = Field(description="Respuesta final al usuario basada solo en los datos suministrados.")
    pasos_sugeridos: list[str]
    advertencias: list[str] = Field(description="Límites, datos sin verificar o recomendaciones de confirmar en sitio.")


# ------------------------------------------------------------------ API
class ChatIn(BaseModel):
    mensaje: str
    lat: float | None = None
    lon: float | None = None


class GeocercaIn(BaseModel):
    nombre: str
    lat: float
    lon: float
    radio_m: float = 150


class EventoGeocercaIn(BaseModel):
    tipo: str  # "entrada" | "salida"
    lat: float | None = None
    lon: float | None = None
