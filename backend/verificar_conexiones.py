"""Comprueba que tus claves funcionan ANTES de abrir la app.

    python verificar_conexiones.py
"""
import herramientas as H
import ia


def main():
    print("== Gemini ==")
    print("Modelo:", ia.modelo(), "| clave configurada:", ia.clave_configurada())
    if ia.clave_configurada():
        try:
            r = ia.cliente().models.generate_content(model=ia.modelo(), contents="Responde solo: Conexión con Gemini exitosa.")
            print("OK ->", (r.text or "").strip())
        except Exception as e:  # noqa: BLE001
            print("FALLÓ ->", ia.traducir_error(e))

    print("\n== Mapas ==")
    print("Proveedor:", H.proveedor_mapas())
    try:
        res = H.geocodificar("Plaza de Bolívar, Bogotá", limite=1)
        print("Geocodificación OK ->", res[0]["direccion"] if res else "sin resultados")
        lugares = H.buscar_lugares_cercanos("combustible", 4.5981, -74.0760, 3000, 3)
        print("Lugares cercanos OK ->", [l["nombre"] for l in lugares])
        ruta = H.calcular_ruta(4.5981, -74.0760, 4.6762, -74.0485, "drive")
        print("Ruta OK ->", ruta["distancia_m"], "m,", ruta["duracion_s"], "s")
    except H.ServicioExternoError as e:
        print("FALLÓ ->", e)


if __name__ == "__main__":
    main()
