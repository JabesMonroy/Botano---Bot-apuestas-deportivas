from __future__ import annotations

import io
import re
import unicodedata


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def ocr(imagen_bytes: bytes) -> str:
    import winocr
    from PIL import Image

    img = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    r = winocr.recognize_pil_sync(img, "es")
    return r["text"] if isinstance(r, dict) else r.text


def _linea_cercana(n: int, disponibles: list[float]) -> float | None:
    objetivo = n + 0.5
    cand = [l for l in disponibles if abs(l - objetivo) <= 1.0]
    return min(cand, key=lambda l: abs(l - objetivo)) if cand else None


CORNERS = [6.5, 7.5, 8.5, 9.5, 10.5, 11.5]
TARJETAS_O = [1.5, 2.5, 3.5, 4.5]
TARJETAS_U = [2.5, 3.5, 4.5, 5.5]


def analizar(texto: str, equipos: list[tuple[str, str, str]]):
    """equipos: lista de (nombre_norm, fifa_code, nombre_display). Devuelve (local, visita, [mercados])."""
    t = _norm(texto)

    hallados = []
    for nombre_norm, fifa, disp in equipos:
        pos = t.find(nombre_norm)
        if pos >= 0:
            hallados.append((pos, fifa, disp))
    hallados.sort()
    orden, vistos = [], set()
    for _pos, fifa, disp in hallados:
        if fifa not in vistos:
            vistos.add(fifa)
            orden.append((fifa, disp))
    local = orden[0] if orden else None
    visita = orden[1] if len(orden) > 1 else None

    mercados: list[str] = []

    for fifa, disp in orden[:2]:
        if re.search(rf"gana\w*\s+{re.escape(_norm(disp))}", t) or re.search(rf"{re.escape(_norm(disp))}\s+gana", t):
            mercados.append("Gana local" if local and fifa == local[0] else "Gana visita")
    if re.search(r"\bempate\b", t):
        mercados.append("Empate")
    if re.search(r"ambos\s+(?:equipos\s+)?(?:anotan|marcan)", t):
        mercados.append("Ambos anotan")

    for m in re.finditer(r"m[a]s de (\d)[.,\s]?5?\s*gol", t):
        mercados.append(f"Más de {m.group(1)}.5 goles")
    for m in re.finditer(r"menos de (\d)[.,\s]?5?\s*gol", t):
        mercados.append(f"Menos de {m.group(1)}.5 goles")

    for m in re.finditer(r"(?:corner|esquina).{0,30}?(mas|menos).{0,8}?(\d{1,2})", t):
        linea = _linea_cercana(int(m.group(2)), CORNERS)
        if linea:
            mercados.append(f"{'Más' if m.group(1) == 'mas' else 'Menos'} de {linea} córners")
    for m in re.finditer(r"tarjeta.{0,30}?(m[a]s|menos).{0,8}?(\d{1,2})", t):
        es_mas = m.group(1) == "mas"
        linea = _linea_cercana(int(m.group(2)), TARJETAS_O if es_mas else TARJETAS_U)
        if linea:
            mercados.append(f"{'Más' if es_mas else 'Menos'} de {linea} tarjetas")

    for m in re.finditer(r"(?:primer|proximo|prox\.?)\s+gol\s+(\w+)", t):
        objetivo = m.group(1)
        if local and objetivo in _norm(local[1]):
            mercados.append("Primer gol: local")
        elif visita and objetivo in _norm(visita[1]):
            mercados.append("Primer gol: visita")

    return local, visita, list(dict.fromkeys(mercados))
