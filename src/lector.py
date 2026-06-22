from __future__ import annotations

import io
import re
import unicodedata

CORNERS = [6.5, 7.5, 8.5, 9.5, 10.5, 11.5]
GOLES = [0.5, 1.5, 2.5, 3.5, 4.5]
TARJETAS_O = [1.5, 2.5, 3.5, 4.5]
TARJETAS_U = [2.5, 3.5, 4.5, 5.5]


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


def _detectar_equipos(texto: str, equipos):
    t = _norm(texto)
    hallados = []
    for nombre_norm, fifa, disp in equipos:
        pos = t.find(nombre_norm)
        if pos >= 0:
            hallados.append((pos, fifa, disp))
    hallados.sort()
    orden, vistos = [], set()
    for _p, fifa, disp in hallados:
        if fifa not in vistos:
            vistos.add(fifa)
            orden.append((fifa, disp))
    return (orden[0] if orden else None, orden[1] if len(orden) > 1 else None)


def _equipo_de(sel: str, equipos):
    for nombre_norm, fifa, _disp in equipos:
        if nombre_norm in sel:
            return fifa
    return None


def _sel_linea(sel: str, palabra: str, lineas_o: list[float], lineas_u: list[float]) -> str | None:
    md = re.search(r"\b(mas|menos)\b", sel)
    if not md:
        return None
    es_mas = md.group(1) == "mas"
    num = re.search(r"(\d+)[.,\s]+5\b", sel) or re.search(r"(\d{1,2})5\b", sel) or re.search(r"(\d+)", sel)
    if not num:
        return None
    linea = _linea_cercana(int(num.group(1)), lineas_o if es_mas else lineas_u)
    if linea is None:
        return None
    return f"{'Más' if es_mas else 'Menos'} de {linea} {palabra}"


def analizar(texto: str, equipos):
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    local, visita = _detectar_equipos(texto, equipos)
    mercados = []
    for i, linea in enumerate(lineas):
        tipo = _norm(linea)
        sel = _norm(lineas[i - 1]) if i > 0 else ""
        m = None
        if "resultado del partido" in tipo:
            fifa = _equipo_de(sel, equipos)
            if local and fifa == local[0]:
                m = "Gana local"
            elif visita and fifa == visita[0]:
                m = "Gana visita"
            elif "empate" in sel:
                m = "Empate"
        elif "proximo gol" in tipo or "gol 1" in tipo or "primer gol" in tipo:
            fifa = _equipo_de(sel, equipos)
            if local and fifa == local[0]:
                m = "Primer gol: local"
            elif visita and fifa == visita[0]:
                m = "Primer gol: visita"
        elif "esquina" in tipo or "corner" in tipo:
            m = _sel_linea(sel, "córners", CORNERS, CORNERS)
        elif "tarjeta" in tipo:
            m = _sel_linea(sel, "tarjetas", TARJETAS_O, TARJETAS_U)
        elif "gol" in tipo and "total" in tipo:
            m = _sel_linea(sel, "goles", GOLES, GOLES)
        elif "ambos" in tipo:
            m = "Ambos anotan"
        if m:
            mercados.append(m)
    return local, visita, list(dict.fromkeys(mercados))
