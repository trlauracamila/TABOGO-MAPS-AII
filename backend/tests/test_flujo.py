"""Pruebas del flujo completo con IA y mapas SIMULADOS (no gastan cuota ni necesitan claves)."""
import io

import pytest
from PIL import Image

import agentes
import chat
import database
import herramientas as H
import ia
from esquemas import AnalisisIA, Recomendacion
from imagenes import gps_exif, preparar_imagen


def _png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 64), "gray").save(b, format="PNG")
    return b.getvalue()


def _analisis(**kw) -> AnalisisIA:
    base = {
        "tipo_solicitud": "identificar_lugar", "resumen_necesidad": "Identificar lugar", "categoria_servicio": "turismo",
        "modo_transporte": "drive",
        "lugar": {"nombre": "Museo del Oro", "categoria": "museo", "direccion_estimada": "", "ciudad": "Bogotá",
                  "pistas_visuales": ["fachada"], "texto_visible": ["MUSEO DEL ORO"]},
        "confianza_identificacion": "alta", "estado_informacion": "suficiente", "motivo_estado": "ok",
        "preguntas_aclaratorias": [], "hechos_observados": ["letrero"], "hipotesis": [],
    }
    base.update(kw)
    return AnalisisIA.model_validate(base)


@pytest.fixture()
def simulados(monkeypatch):
    def fake_ia(prompt, esquema, imagen_bytes=None, mime_type="image/jpeg"):
        if esquema is AnalisisIA:
            return fake_ia.analisis
        return Recomendacion(titulo="Museo del Oro", resumen="Está cerca.", pasos_sugeridos=["Camina"], advertencias=[])
    fake_ia.analisis = _analisis()
    monkeypatch.setattr(ia, "generar_estructurado", fake_ia)
    monkeypatch.setattr(H, "geocodificar_inverso", lambda lat, lon: {"direccion": "Cra 7, Bogotá", "ciudad": "Bogotá",
                                                                    "barrio": "Centro", "lat": lat, "lon": lon, "fuente": "x"})
    monkeypatch.setattr(H, "geocodificar", lambda t, a=None, b=None, l=5: [
        {"nombre": "Museo del Oro", "direccion": "Carrera 6 #15-88, Bogotá", "lat": 4.6019, "lon": -74.0719,
         "categoria": "museum", "fuente": "geoapify"}])
    monkeypatch.setattr(H, "buscar_lugares_cercanos", lambda c, la, lo, r=2000, l=8: [
        {"nombre": "Gasolinera X", "direccion": "Av 1", "lat": 4.60, "lon": -74.07, "categoria": c, "fuente": "geoapify"}])
    monkeypatch.setattr(H, "calcular_ruta", lambda *a, **k: {
        "distancia_m": 800, "duracion_s": 600, "geometria": [[4.6, -74.07], [4.6019, -74.0719]],
        "pasos": ["Gira a la derecha"], "modo": "drive", "fuente": "geoapify"})
    return fake_ia


def test_flujo_completo_foto_identifica_lugar(cliente, simulados):
    r = cliente.post("/api/analizar-caso", data={"descripcion": "¿Qué lugar es este?", "lat": 4.5981, "lon": -74.0760},
                     files={"imagen": ("foto.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    caso = r.json()
    assert caso["estado"] == "completado"
    assert caso["geo"]["destino"]["nombre"] == "Museo del Oro"
    assert caso["geo"]["verificacion"] == "confirmado_por_mapa"
    assert caso["geo"]["ruta"]["distancia_m"] == 800
    agentes_usados = [t["agente"] for t in caso["traza"]]
    assert agentes_usados == ["Agente de Contexto", "Agente de Visión", "Agente de Geolocalización", "Agente de Acción"]
    ejecutadas = {a["tipo"] for a in caso["acciones"] if a["estado"] == "ejecutada"}
    assert ejecutadas == {"crear_geocerca", "guardar_caso"}
    # la acción dejó un cambio real en el sistema
    geos = cliente.get("/api/geocercas").json()
    assert len(geos) == 1 and geos[0]["origen"] == "ia" and geos[0]["caso_id"] == caso["id"]
    # persistencia + trazabilidad
    guardado = cliente.get(f"/api/casos/{caso['id']}").json()
    assert guardado["traza"] and guardado["acciones"] and guardado["recomendacion"]["titulo"]
    assert cliente.get("/api/casos").json()[0]["agentes"][0] == "Agente de Contexto"


def test_informacion_insuficiente_no_ejecuta_acciones(cliente, simulados):
    simulados.analisis = _analisis(estado_informacion="insuficiente", motivo_estado="Foto borrosa",
                                   preguntas_aclaratorias=["¿Puedes tomar otra foto?"],
                                   lugar={"nombre": "", "categoria": "", "direccion_estimada": "", "ciudad": "",
                                          "pistas_visuales": [], "texto_visible": []}, confianza_identificacion="baja")
    caso = cliente.post("/api/analizar-caso", data={"descripcion": "foto"}).json()
    assert caso["estado"] == "requiere_informacion"
    assert [t["agente"] for t in caso["traza"]][-1] == "Validación (orquestador)"
    assert "Agente de Geolocalización" not in [t["agente"] for t in caso["traza"]]
    assert cliente.get("/api/geocercas").json() == []


def test_contradictoria_y_no_corresponde(cliente, simulados):
    for estado in ("contradictoria", "no_corresponde"):
        simulados.analisis = _analisis(estado_informacion=estado, motivo_estado="x")
        assert cliente.post("/api/analizar-caso", data={"descripcion": "algo"}).json()["estado"] == "requiere_informacion"


def test_buscar_servicio_sin_gps_pide_ubicacion(cliente, simulados):
    simulados.analisis = _analisis(tipo_solicitud="buscar_servicio", categoria_servicio="combustible",
                                   lugar={"nombre": "", "categoria": "", "direccion_estimada": "", "ciudad": "",
                                          "pistas_visuales": [], "texto_visible": []})
    caso = cliente.post("/api/analizar-caso", data={"descripcion": "necesito gasolina"}).json()
    assert caso["estado"] == "requiere_informacion" and "ubicación" in caso["recomendacion"]["resumen"]


def test_buscar_servicio_con_gps_elige_el_mas_cercano(cliente, simulados):
    simulados.analisis = _analisis(tipo_solicitud="buscar_servicio", categoria_servicio="combustible",
                                   lugar={"nombre": "", "categoria": "", "direccion_estimada": "", "ciudad": "",
                                          "pistas_visuales": [], "texto_visible": []})
    caso = cliente.post("/api/analizar-caso", data={"descripcion": "necesito gasolina", "lat": 4.6, "lon": -74.07}).json()
    assert caso["estado"] == "completado"
    assert caso["geo"]["verificacion"] == "datos_consultados"
    assert caso["geo"]["destino"]["distancia_m"] <= min(c["distancia_m"] for c in caso["geo"]["candidatos"])
    assert "datos_propios" in {c["fuente"] for c in caso["geo"]["candidatos"]}


def test_sin_texto_ni_foto_es_400(cliente):
    assert cliente.post("/api/analizar-caso", data={"descripcion": ""}).status_code == 400


def test_error_de_ia_es_502_legible(cliente, monkeypatch):
    def falla(*a, **k):
        raise ia.ErrorIA("Se alcanzó el límite")
    monkeypatch.setattr(ia, "generar_estructurado", falla)
    monkeypatch.setattr(H, "geocodificar_inverso", lambda *a: {"direccion": None, "ciudad": None})
    r = cliente.post("/api/analizar-caso", data={"descripcion": "hola", "lat": 4.6, "lon": -74.07})
    assert r.status_code == 502 and "límite" in r.json()["detail"]


def test_chat_con_herramientas_y_persistencia(cliente, simulados, monkeypatch):
    caso = cliente.post("/api/analizar-caso", data={"descripcion": "¿Qué lugar es?", "lat": 4.5981, "lon": -74.0760}).json()

    def fake_modelo(sistema, historial, mensaje, herramientas):
        assert "Museo del Oro" in sistema  # el contexto del caso llega al modelo
        nombres = {f.__name__ for f in herramientas}
        assert nombres == {"consultar_servicios_propios", "buscar_lugares_cercanos", "geocodificar", "calcular_ruta",
                           "crear_geocerca"}
        crear = next(f for f in herramientas if f.__name__ == "crear_geocerca")
        crear("Zona museo", 4.6019, -74.0719, 100)
        return "Listo, creé la geocerca."
    monkeypatch.setattr(chat, "_llamar_modelo", fake_modelo)
    r = cliente.post(f"/api/casos/{caso['id']}/chat", json={"mensaje": "crea una geocerca de 100 m"}).json()
    assert r["geocerca_creada"] and r["herramientas"][0]["nombre"] == "crear_geocerca"
    msgs = cliente.get(f"/api/casos/{caso['id']}/mensajes").json()
    assert [m["rol"] for m in msgs] == ["user", "assistant"] and msgs[1]["herramientas"][0]["ok"]
    assert len(cliente.get("/api/geocercas").json()) == 2
    assert cliente.post("/api/casos/NOEXISTE/chat", json={"mensaje": "hola"}).status_code == 404


def test_geocercas_crud_y_eventos(cliente):
    g = cliente.post("/api/geocercas", json={"nombre": "Casa", "lat": 4.6, "lon": -74.07, "radio_m": 200}).json()
    assert g["radio_m"] == 200
    ev = cliente.post(f"/api/geocercas/{g['id']}/eventos", json={"tipo": "entrada", "lat": 4.6, "lon": -74.07})
    assert ev.status_code == 200
    assert cliente.post(f"/api/geocercas/{g['id']}/eventos", json={"tipo": "otro"}).status_code == 400
    assert cliente.get("/api/eventos-geocerca").json()[0]["geocerca"] == "Casa"
    assert cliente.delete(f"/api/geocercas/{g['id']}").status_code == 200
    assert cliente.get("/api/geocercas").json() == []


def test_datos_propios_sembrados(cliente):
    assert len(cliente.get("/api/servicios").json()) >= 10
    cerca = H.consultar_servicios_propios(lat=4.5981, lon=-74.0760, radio_m=1500)
    assert cerca and cerca[0]["distancia_m"] <= cerca[-1]["distancia_m"]


def test_geoapify_parseo_con_respuestas_simuladas(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", "clave-de-prueba")
    def fake(url, params, nominatim=False):
        if "geocode/search" in url:
            return {"results": [{"name": "Museo del Oro", "formatted": "Museo del Oro, Bogotá", "lat": 4.6, "lon": -74.07}]}
        if "geocode/reverse" in url:
            return {"results": [{"formatted": "Cra 7, Bogotá", "city": "Bogotá", "suburb": "Centro"}]}
        if "v2/places" in url:
            assert params["categories"] == "service.vehicle.fuel" and params["filter"].startswith("circle:-74.07,4.6")
            return {"features": [{"properties": {"name": "EDS 1", "formatted": "Av 1", "lat": 4.601, "lon": -74.071}}]}
        if "routing" in url:
            assert params["waypoints"] == "4.6,-74.07|4.7,-74.0"
            return {"features": [{"properties": {"distance": 1234, "time": 321, "legs": [{"steps": [
                {"instruction": {"text": "Sigue recto"}}]}]},
                "geometry": {"type": "MultiLineString", "coordinates": [[[-74.07, 4.6], [-74.0, 4.7]]]}}]}
    monkeypatch.setattr(H, "_get_json", fake)
    assert H.proveedor_mapas() == "geoapify"
    assert H.geocodificar("museo", 4.6, -74.07)[0]["fuente"] == "geoapify"
    assert H.geocodificar_inverso(4.6, -74.07)["ciudad"] == "Bogotá"
    assert H.buscar_lugares_cercanos("combustible", 4.6, -74.07)[0]["nombre"] == "EDS 1"
    r = H.calcular_ruta(4.6, -74.07, 4.7, -74.0)
    assert r["distancia_m"] == 1234 and r["geometria"][0] == [4.6, -74.07] and r["pasos"] == ["Sigue recto"]


def test_exif_gps_y_redimensionado():
    img = Image.new("RGB", (3000, 2000), "red")
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (4.0, 36.0, 0.0), 3: "W", 4: (74.0, 3.0, 0.0)}
    b = io.BytesIO()
    img.save(b, format="JPEG", exif=exif)
    datos, mime, gps = preparar_imagen(b.getvalue())
    assert mime == "image/jpeg" and gps and abs(gps["lat"] - 4.6) < 1e-6 and abs(gps["lon"] + 74.05) < 1e-6
    assert max(Image.open(io.BytesIO(datos)).size) <= 1600
    assert preparar_imagen(b"no es imagen")[2] is None


def test_similitud_nombres():
    assert H.similitud_nombre("Museo del Oro", "Museo del Oro (Banco de la República)") >= 0.6
    assert H.similitud_nombre("Museo del Oro", "Centro Comercial Andino") < 0.6
