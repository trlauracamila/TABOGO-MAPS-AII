"""Preparación de la foto: reduce tamaño y lee coordenadas GPS del EXIF (si la foto las trae)."""
import io

from PIL import Image, ImageOps

MAX_LADO = 1600


def _a_grados(valor, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in valor)
        grados = d + m / 60.0 + s / 3600.0
        return -grados if ref in ("S", "W") else grados
    except Exception:  # noqa: BLE001
        return None


def gps_exif(img: Image.Image) -> dict | None:
    try:
        gps = img.getexif().get_ifd(0x8825)
    except Exception:  # noqa: BLE001
        return None
    if not gps or 2 not in gps or 4 not in gps:
        return None
    lat = _a_grados(gps[2], gps.get(1))
    lon = _a_grados(gps[4], gps.get(3))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"lat": lat, "lon": lon, "fuente": "exif"}


def preparar_imagen(datos: bytes, mime_original: str = "image/jpeg") -> tuple[bytes, str, dict | None]:
    """Devuelve (bytes_jpeg, mime, gps_exif|None). Si Pillow no puede leerla, la devuelve tal cual."""
    try:
        img = Image.open(io.BytesIO(datos))
        gps = gps_exif(img)
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((MAX_LADO, MAX_LADO))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg", gps
    except Exception:  # noqa: BLE001
        return datos, mime_original or "image/jpeg", None
