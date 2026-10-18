"""Agentes especializados y orquestación (LangGraph).

Flujo:
  START -> Agente de Contexto -> Agente de Visión -> [decisión] -> Agente de Geolocalización -> Agente de Acción -> END
                                                        └-> Validación (pide más información) -> END

  Agente de Contexto        : herramientas (BD propia + geocodificación inversa). No usa IA generativa.
  Agente de Visión          : Gemini multimodal (texto + foto) -> AnalisisIA estructurado.
  Agente de Geolocalización : herramientas de mapas (geocodificar, lugares cercanos, ruta) + BD propia.
                              Verifica contra el mapa lo que la IA dijo ver. No usa IA generativa.
  Agente de Acción          : Gemini (redacta la recomendación SOLO con datos consultados) y EJECUTA acciones
                              reales: crear geocerca y guardar el caso.
  Orquestación              : condiciones del grafo (decidir_ruta) determinan qué agentes participan.
"""
import operator
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

import database
import herramientas as H
import ia
from esquemas import AnalisisIA, Recomendacion

RADIO_GEOCERCA_M = 150


class Estado(TypedDict, total=False):
    caso_id: str
    creado_en: str
    descripcion: str
    ubicacion: dict | None
    exif_gps: dict | None
    imagen_bytes: bytes | None
    mime_type: str
    imagen_nombre: str | None
    contexto: dict
    analisis: dict
    geo: dict
    recomendacion: dict
    acciones: list
    caso_final: dict
    traza: Annotated[list, operator.add]


def _entrada_traza(agente, responsabilidad, herramientas, t0, salida, usa_ia=False):
    return {"agente": agente, "responsabilidad": responsabilidad, "usa_ia": usa_ia,
            "herramientas": herramientas, "salida": salida,
            "ms": round((time.perf_counter() - t0) * 1000)}


# ======================================================== AGENTE 1: CONTEXTO
def agente_contexto(estado: Estado):
    t0 = time.perf_counter()
    herr: list = []
    ctx = {"direccion_usuario": None, "ciudad_usuario": None, "servicios_propios_cercanos": []}
    ub = estado.get("ubicacion") or estado.get("exif_gps")
    if ub:
        inv = H.registrar_uso(herr, "geocodificar_inverso", {"lat": ub["lat"], "lon": ub["lon"]},
                              lambda: H.geocodificar_inverso(ub["lat"], ub["lon"]))
        if inv:
            ctx["direccion_usuario"] = inv.get("direccion")
            ctx["ciudad_usuario"] = inv.get("ciudad")
        propios = H.registrar_uso(herr, "consultar_servicios_propios", {"radio_m": 2000},
                                  lambda: H.consultar_servicios_propios(lat=ub["lat"], lon=ub["lon"], radio_m=2000, limite=6))
        ctx["servicios_propios_cercanos"] = [{"nombre": s["nombre"], "categoria": s["categoria"],
                                              "distancia_m": s.get("distancia_m")} for s in (propios or [])]
    salida = ("Ubicación disponible: " + (ctx["direccion_usuario"] or "sin dirección")) if ub else "Sin ubicación del usuario"
    return {"contexto": ctx,
            "traza": [_entrada_traza("Agente de Contexto", "Reunir ubicación y datos propios cercanos", herr, t0, salida)]}


# ========================================================== AGENTE 2: VISIÓN
def _prompt_vision(estado: Estado) -> str:
    ctx = estado.get("contexto", {})
    gps = estado.get("ubicacion")
    exif = estado.get("exif_gps")
    return f"""Eres el Agente de Visión de una app de movilidad urbana. Analizas el texto del usuario y, si existe,
una FOTO de un lugar, para identificar el lugar o entender qué servicio necesita.

TEXTO DEL USUARIO: {estado['descripcion']}
¿Adjuntó foto?: {'sí' if estado.get('imagen_bytes') else 'no'}
UBICACIÓN GPS DEL USUARIO: {gps if gps else 'no disponible'}
DIRECCIÓN APROXIMADA DEL USUARIO (consultada en el mapa): {ctx.get('direccion_usuario') or 'no disponible'}
COORDENADAS EXIF DE LA FOTO: {exif if exif else 'la foto no trae coordenadas'}
SERVICIOS PROPIOS CERCANOS (datos de la app): {ctx.get('servicios_propios_cercanos') or 'ninguno'}

CATEGORÍAS PERMITIDAS para categoria_servicio: {', '.join(H.CATEGORIAS)} o "ninguna".

TIPOS DE SOLICITUD:
- identificar_lugar: el usuario quiere saber qué lugar muestra la foto / dónde está.
- buscar_servicio: quiere encontrar un servicio cercano (gasolinera, parqueadero, hospital...).
- como_llegar: quiere llegar a un lugar concreto (lugar.nombre = ese destino).
- otro: nada de lo anterior.

REGLAS ESTRICTAS:
- Identifica el lugar usando letreros, texto visible, logotipos, arquitectura o monumentos inconfundibles.
- NO inventes. Si no puedes identificarlo con certeza, deja lugar.nombre vacío y confianza_identificacion "baja".
- confianza "alta" solo con texto/letrero legible o un monumento inconfundible; "media" con coincidencia visual
  fuerte pero sin texto; "baja" en los demás casos.
- direccion_estimada solo si aparece escrita en la imagen; si no, cadena vacía. No supongas direcciones.
- Separa hechos_observados (lo que ves) de hipotesis (lo que supones).
- estado_informacion: "insuficiente" si falta información para actuar; "contradictoria" si la foto y el texto
  no coinciden entre sí o con la ubicación; "no_corresponde" si la imagen/solicitud no tiene relación con
  lugares, movilidad o servicios urbanos; si no, "suficiente".
- Si el estado no es "suficiente", escribe hasta 3 preguntas_aclaratorias concretas.
- modo_transporte: "walk" si menciona caminar, "bicycle" si menciona bicicleta, en otro caso "drive".
"""


def agente_vision(estado: Estado):
    t0 = time.perf_counter()
    res = ia.generar_estructurado(_prompt_vision(estado), AnalisisIA,
                                  imagen_bytes=estado.get("imagen_bytes"), mime_type=estado.get("mime_type", "image/jpeg"))
    a = res.model_dump(mode="json")
    if a["categoria_servicio"] not in H.CATEGORIAS:
        a["categoria_servicio"] = "ninguna"
    salida = f"{a['tipo_solicitud']} | información {a['estado_informacion']} | confianza {a['confianza_identificacion']}"
    return {"analisis": a,
            "traza": [_entrada_traza("Agente de Visión", "Analizar texto + foto y producir resultado estructurado",
                                     [], t0, salida, usa_ia=True)]}


# ============================================== ORQUESTACIÓN (decisión)
def _faltantes(estado: Estado) -> list[str]:
    a = estado["analisis"]
    lugar = a["lugar"]
    tipo = a["tipo_solicitud"]
    falt: list[str] = []
    if a["estado_informacion"] != "suficiente":
        etiqueta = {"insuficiente": "Información insuficiente", "contradictoria": "Información contradictoria",
                    "no_corresponde": "La solicitud no corresponde al caso de uso"}[a["estado_informacion"]]
        falt.append(f"{etiqueta}: {a['motivo_estado'] or 'sin detalle'}")
        return falt
    if tipo == "identificar_lugar" and (not lugar["nombre"].strip() or a["confianza_identificacion"] == "baja"):
        falt.append("No se pudo identificar el lugar con suficiente certeza a partir de la foto y el texto.")
    if tipo == "como_llegar" and not lugar["nombre"].strip():
        falt.append("No quedó claro a qué lugar quieres llegar.")
    if tipo == "buscar_servicio" and a["categoria_servicio"] not in H.CATEGORIAS:
        falt.append("No se pudo determinar qué tipo de servicio buscas.")
    if tipo == "otro":
        falt.append("La solicitud no es identificar un lugar, buscar un servicio ni pedir una ruta.")
    if tipo in ("buscar_servicio", "como_llegar") and not estado.get("ubicacion"):
        falt.append("Necesito tu ubicación: activa el GPS del navegador o haz clic en el mapa (modo simulación).")
    return falt


def decidir_ruta(estado: Estado) -> str:
    """Condición de orquestación: ¿hay información suficiente para pasar al Agente de Geolocalización?"""
    return "validacion" if _faltantes(estado) else "agente_geo"


def _ensamblar(estado: Estado, estado_caso: str, geo, rec, acciones, traza) -> dict:
    return {"id": estado["caso_id"], "creado_en": estado["creado_en"], "descripcion": estado["descripcion"],
            "ubicacion": estado.get("ubicacion"), "imagen_nombre": estado.get("imagen_nombre"),
            "estado": estado_caso, "analisis": estado["analisis"], "geo": geo, "recomendacion": rec,
            "acciones": acciones, "traza": traza}


def nodo_validacion(estado: Estado):
    """Regla del orquestador: si falta información, se pide al usuario y NO se ejecutan acciones de mapa."""
    t0 = time.perf_counter()
    falt = _faltantes(estado)
    a = estado["analisis"]
    rec = {"titulo": "Necesito más información", "resumen": " ".join(falt),
           "pasos_sugeridos": a["preguntas_aclaratorias"] or ["Describe con más detalle lo que necesitas o adjunta otra foto."],
           "advertencias": []}
    entrada = _entrada_traza("Validación (orquestador)", "Detectar información insuficiente/contradictoria",
                             [], t0, "; ".join(falt))
    acciones = [{"tipo": "crear_geocerca", "estado": "omitida", "detalle": "Información insuficiente"},
                {"tipo": "guardar_caso", "estado": "ejecutada", "id": estado["caso_id"],
                 "detalle": "Caso guardado como 'requiere_informacion'"}]
    caso = _ensamblar(estado, "requiere_informacion", None, rec, acciones, estado.get("traza", []) + [entrada])
    database.guardar_caso(caso)
    return {"recomendacion": rec, "acciones": acciones, "caso_final": caso, "traza": [entrada]}


# ============================================ AGENTE 3: GEOLOCALIZACIÓN
def _dedup(cands: list[dict]) -> list[dict]:
    vistos, salida = set(), []
    for c in cands:
        clave = (H._normalizar(c["nombre"]), round(c["lat"], 3), round(c["lon"], 3))
        if clave not in vistos:
            vistos.add(clave)
            salida.append(c)
    return salida


def agente_geo(estado: Estado):
    t0 = time.perf_counter()
    herr: list = []
    a = estado["analisis"]
    lugar, tipo = a["lugar"], a["tipo_solicitud"]
    gps, exif = estado.get("ubicacion"), estado.get("exif_gps")
    ref = exif or gps  # punto de referencia para sesgar la búsqueda
    rlat, rlon = (ref["lat"], ref["lon"]) if ref else (None, None)
    ctx = estado.get("contexto", {})
    notas: list[str] = []
    cands: list[dict] = []

    if tipo in ("identificar_lugar", "como_llegar") and lugar["nombre"].strip():
        ciudad = lugar["ciudad"] or ctx.get("ciudad_usuario") or ""
        texto = f"{lugar['nombre']} {ciudad}".strip()
        geoc = H.registrar_uso(herr, "geocodificar", {"texto": texto, "cerca": ref},
                               lambda: H.geocodificar(texto, rlat, rlon)) or []
        for c in geoc:
            c["similitud"] = H.similitud_nombre(lugar["nombre"], c["nombre"])
        cands += geoc
        propios = H.registrar_uso(herr, "consultar_servicios_propios", {"texto": lugar["nombre"]},
                                  lambda: H.consultar_servicios_propios(lat=rlat, lon=rlon, radio_m=40000, limite=100)) or []
        for p in propios:
            sim = H.similitud_nombre(lugar["nombre"], p["nombre"])
            if sim >= 0.6:
                cands.append({"nombre": p["nombre"], "direccion": p.get("direccion"), "lat": p["lat"], "lon": p["lon"],
                              "categoria": p["categoria"], "fuente": "datos_propios", "similitud": sim})

    cat = a["categoria_servicio"]
    if tipo == "buscar_servicio" or (not cands and cat in H.CATEGORIAS and ref):
        if cat in H.CATEGORIAS and ref:
            cerca = H.registrar_uso(herr, "buscar_lugares_cercanos", {"categoria": cat, "radio_m": 2000},
                                    lambda: H.buscar_lugares_cercanos(cat, rlat, rlon, 2000, 8)) or []
            if not cerca:
                cerca = H.registrar_uso(herr, "buscar_lugares_cercanos", {"categoria": cat, "radio_m": 6000},
                                        lambda: H.buscar_lugares_cercanos(cat, rlat, rlon, 6000, 8)) or []
            cands += cerca
            propios = H.registrar_uso(herr, "consultar_servicios_propios", {"categoria": cat, "radio_m": 6000},
                                      lambda: H.consultar_servicios_propios(categoria=cat, lat=rlat, lon=rlon,
                                                                            radio_m=6000, limite=5)) or []
            cands += [{"nombre": p["nombre"], "direccion": p.get("direccion"), "lat": p["lat"], "lon": p["lon"],
                       "categoria": p["categoria"], "fuente": "datos_propios"} for p in propios]

    origen = gps
    if origen:
        for c in cands:
            c["distancia_m"] = round(H.haversine_m(origen["lat"], origen["lon"], c["lat"], c["lon"]))
    cands = _dedup(cands)

    # ---- elegir destino y verificar contra el mapa
    destino, verificacion = None, "sin_resultados"
    if cands:
        if tipo == "buscar_servicio":
            destino = min(cands, key=lambda c: c.get("distancia_m", 10**9))
            verificacion = "datos_consultados"
        else:
            destino = max(cands, key=lambda c: (c.get("similitud", 0), -c.get("distancia_m", 0)))
            verificacion = "confirmado_por_mapa" if destino.get("similitud", 0) >= 0.6 else "parcial"
            if verificacion == "parcial":
                notas.append("El nombre que vio la IA no coincide exactamente con el resultado del mapa; confirma en sitio.")
            if exif:
                d_exif = H.haversine_m(exif["lat"], exif["lon"], destino["lat"], destino["lon"])
                if d_exif > 1500:
                    verificacion = "parcial"
                    notas.append(f"El lugar encontrado queda a {round(d_exif)} m de donde se tomó la foto (EXIF).")
                elif d_exif <= 300:
                    notas.append("El resultado coincide con las coordenadas EXIF de la foto.")
    else:
        notas.append("No se encontraron lugares en el servicio de mapas ni en los datos propios.")

    ruta = None
    if destino and origen:
        ruta = H.registrar_uso(
            herr, "calcular_ruta", {"modo": a["modo_transporte"], "destino": destino["nombre"]},
            lambda: H.calcular_ruta(origen["lat"], origen["lon"], destino["lat"], destino["lon"], a["modo_transporte"]))
        if ruta is None:
            notas.append("No se pudo calcular la ruta con el servicio de mapas.")
    elif destino and not origen:
        notas.append("Sin ubicación del usuario no se calculó ruta.")

    geo = {"origen": origen, "ubicacion_foto": exif, "direccion_usuario": ctx.get("direccion_usuario"),
           "candidatos": cands[:6], "destino": destino, "verificacion": verificacion, "ruta": ruta,
           "notas": notas, "proveedor_mapas": H.proveedor_mapas()}
    salida = (f"Destino: {destino['nombre']} ({verificacion})" if destino else "Sin destino") + \
             (f" | ruta {ruta['distancia_m']} m" if ruta else "")
    return {"geo": geo, "traza": [_entrada_traza("Agente de Geolocalización",
                                                 "Verificar y localizar con mapas + datos propios, calcular ruta",
                                                 herr, t0, salida)]}


# ================================================= AGENTE 4: ACCIÓN
def _prompt_accion(estado: Estado) -> str:
    import json
    geo, a = estado["geo"], estado["analisis"]
    ruta = geo.get("ruta")
    destino = geo.get("destino")
    datos = {
        "solicitud_del_usuario": estado["descripcion"], "tipo_solicitud": a["tipo_solicitud"],
        "lugar_que_cree_ver_la_ia": a["lugar"]["nombre"] or None, "confianza_ia": a["confianza_identificacion"],
        "hechos_observados": a["hechos_observados"], "hipotesis_no_confirmadas": a["hipotesis"],
        "destino_elegido_por_el_mapa": ({k: destino.get(k) for k in ("nombre", "direccion", "distancia_m", "fuente")}
                                        if destino else None),
        "verificacion": geo["verificacion"],
        "otros_candidatos": [{"nombre": c["nombre"], "direccion": c.get("direccion"), "distancia_m": c.get("distancia_m")}
                             for c in geo["candidatos"] if c is not destino][:4],
        "ruta": ({"distancia_m": ruta["distancia_m"], "duracion_s": ruta["duracion_s"], "modo": ruta["modo"],
                  "primeros_pasos": ruta["pasos"][:5]} if ruta else None),
        "direccion_actual_del_usuario": geo.get("direccion_usuario"), "notas_del_agente_geo": geo["notas"],
    }
    return f"""Eres el Agente de Acción. Redacta la respuesta final para el usuario usando ÚNICAMENTE estos datos:
{json.dumps(datos, ensure_ascii=False, indent=1)}

REGLAS:
- La dirección oficial es la de "destino_elegido_por_el_mapa" (consultada en el servicio de mapas), no la de la IA.
- Si verificacion es "parcial" o "sin_resultados", dilo claramente en advertencias y pide confirmar en sitio.
- Distingue hechos de hipótesis. No inventes horarios, precios, teléfonos ni datos que no estén arriba.
- Si hay ruta, menciona distancia y tiempo aproximado (convierte segundos a minutos).
- Aclara en advertencias que se creó una geocerca alrededor del destino SOLO si hay destino.
- resumen: máximo 120 palabras, en español. pasos_sugeridos: 2 a 4 pasos."""


def agente_accion(estado: Estado):
    t0 = time.perf_counter()
    herr: list = []
    geo = estado["geo"]
    destino = geo.get("destino")
    rec = ia.generar_estructurado(_prompt_accion(estado), Recomendacion).model_dump(mode="json")

    acciones: list = []
    if destino:
        g = H.registrar_uso(herr, "crear_geocerca", {"nombre": destino["nombre"], "radio_m": RADIO_GEOCERCA_M},
                            lambda: H.crear_geocerca(f"Geocerca: {destino['nombre']}", destino["lat"], destino["lon"],
                                                     RADIO_GEOCERCA_M, origen="ia", caso_id=estado["caso_id"]))
        if g:
            acciones.append({"tipo": "crear_geocerca", "estado": "ejecutada", "id": g["id"],
                             "detalle": f"Geocerca de {int(g['radio_m'])} m alrededor de {destino['nombre']}", "datos": g})
        else:
            acciones.append({"tipo": "crear_geocerca", "estado": "fallida", "detalle": "No se pudo crear la geocerca"})
    else:
        acciones.append({"tipo": "crear_geocerca", "estado": "omitida", "detalle": "No hay destino para delimitar"})

    estado_caso = "completado" if destino else "sin_resultados"
    acciones.append({"tipo": "guardar_caso", "estado": "ejecutada", "id": estado["caso_id"],
                     "detalle": f"Caso guardado en SQLite con estado '{estado_caso}'"})
    entrada = _entrada_traza("Agente de Acción", "Redactar recomendación fundamentada y ejecutar acciones", herr, t0,
                             "; ".join(f"{x['tipo']}: {x['estado']}" for x in acciones), usa_ia=True)
    caso = _ensamblar(estado, estado_caso, geo, rec, acciones, estado.get("traza", []) + [entrada])
    database.guardar_caso(caso)
    return {"recomendacion": rec, "acciones": acciones, "caso_final": caso, "traza": [entrada]}


# ============================================================ GRAFO
def crear_orquestador():
    g = StateGraph(Estado)
    g.add_node("agente_contexto", agente_contexto)
    g.add_node("agente_vision", agente_vision)
    g.add_node("validacion", nodo_validacion)
    g.add_node("agente_geo", agente_geo)
    g.add_node("agente_accion", agente_accion)
    g.add_edge(START, "agente_contexto")
    g.add_edge("agente_contexto", "agente_vision")
    g.add_conditional_edges("agente_vision", decidir_ruta, {"agente_geo": "agente_geo", "validacion": "validacion"})
    g.add_edge("agente_geo", "agente_accion")
    g.add_edge("agente_accion", END)
    g.add_edge("validacion", END)
    return g.compile()
