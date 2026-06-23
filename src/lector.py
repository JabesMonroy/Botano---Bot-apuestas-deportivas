from __future__ import annotations

import io
import os
import re
import unicodedata

CORNERS = [6.5, 7.5, 8.5, 9.5, 10.5, 11.5]
GOLES = [0.5, 1.5, 2.5, 3.5, 4.5]
TARJETAS_O = [1.5, 2.5, 3.5, 4.5]
TARJETAS_U = [2.5, 3.5, 4.5, 5.5]

ALIAS = {
    "COD": ["republica democratica del congo", "rd congo", "dr congo"],
    "KOR": ["corea del sur", "korea republic", "republica de corea"],
    "PRK": ["corea del norte"],
    "USA": ["estados unidos", "united states"],
    "KSA": ["arabia saudita", "arabia saudi", "saudi arabia"],
    "RSA": ["sudafrica", "south africa"],
    "CRC": ["costa rica"],
    "UAE": ["emiratos arabes unidos"],
    "CIV": ["costa de marfil", "ivory coast"],
    "CPV": ["cabo verde", "cape verde"],
}

TIPOS_MERCADO = [
    ("resultado del partido", "1x2"),
    ("doble oportunidad", "doble"),
    ("goles totales", "goles"),
    ("tarjetas totales", "tarj"),
    ("tiros de esquina", "corn"),
    ("proximo gol", "pg"),
    ("primer gol", "pg"),
    ("ambos", "btts"),
]


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def ocr(imagen_bytes: bytes) -> str:
    key = os.environ.get("OCR_SPACE_API_KEY")
    if key:
        return _ocr_space(imagen_bytes, key)
    import winocr
    from PIL import Image

    img = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    r = winocr.recognize_pil_sync(img, "es")
    return r["text"] if isinstance(r, dict) else r.text


def _ocr_space(imagen_bytes: bytes, api_key: str) -> str:
    import base64

    import httpx

    b64 = base64.b64encode(imagen_bytes).decode()
    r = httpx.post(
        "https://api.ocr.space/parse/image",
        data={
            "apikey": api_key,
            "language": "spa",
            "OCREngine": "2",
            "scale": "true",
            "base64Image": "data:image/png;base64," + b64,
        },
        timeout=60,
    )
    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code != 200:
        raise RuntimeError(f"OCR.space {r.status_code}: {r.text[:200]}")
    if data.get("IsErroredOnProcessing"):
        em = data.get("ErrorMessage")
        raise RuntimeError(em[0] if isinstance(em, list) and em else str(em))
    res = data.get("ParsedResults") or []
    return res[0].get("ParsedText", "") if res else ""


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
    sel = re.sub(r"m[a]s\s*/\s*menos|menos\s*/\s*m[a]s", " ", sel)
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
    t = _norm(texto)
    local, visita = _detectar_equipos(texto, equipos)
    mercados = []

    for nombre_norm, fifa, _disp in equipos:
        lado = "l" if (local and fifa == local[0]) else ("v" if (visita and fifa == visita[0]) else None)
        if lado is None:
            continue
        if re.search(rf"{re.escape(nombre_norm)}\s+resultado del partido", t):
            mercados.append("Gana local" if lado == "l" else "Gana visita")
        if re.search(rf"{re.escape(nombre_norm)}\s+(?:proximo|primer) gol", t):
            mercados.append("Primer gol: local" if lado == "l" else "Primer gol: visita")
    if re.search(r"empate\s+resultado del partido", t):
        mercados.append("Empate")
    if re.search(r"ambos\s+(?:equipos\s+)?(?:anotan|marcan)", t):
        mercados.append("Ambos anotan")

    def _ou(patron: str, palabra: str, lo, lu):
        for m in re.finditer(rf"(mas|menos)\s*(?:de\s*)?(\d+)[.,\s]*5?\s+{patron}", t):
            linea = _linea_cercana(int(m.group(2)), lo if m.group(1) == "mas" else lu)
            if linea is not None:
                mercados.append(f"{'Más' if m.group(1) == 'mas' else 'Menos'} de {linea} {palabra}")

    _ou(r"tarjetas?", "tarjetas", TARJETAS_O, TARJETAS_U)
    _ou(r"goles?\s+total", "goles", GOLES, GOLES)
    _ou(r"(?:tiros de esquina|corner)", "córners", CORNERS, CORNERS)
    return local, visita, list(dict.fromkeys(mercados))


def _fifa_en(seg: str, fifa: str, equipos) -> bool:
    return any(f == fifa and nn in seg for nn, f, _d in equipos)


def _mercado_seg(seg: str, fam: str, lf: str, vf: str, equipos):
    if fam == "1x2":
        if _fifa_en(seg, lf, equipos):
            return "Gana local"
        if _fifa_en(seg, vf, equipos):
            return "Gana visita"
        if "empate" in seg:
            return "Empate"
        return None
    if fam == "doble":
        if re.search(r"\b1\s*x\b", seg):
            return "Local o empate (1X)"
        if re.search(r"\bx\s*2\b", seg):
            return "Empate o visita (X2)"
        if re.search(r"\b12\b", seg):
            return "Local o visita, no empate (12)"
        return None
    if fam == "pg":
        if _fifa_en(seg, lf, equipos):
            return "Primer gol: local"
        if _fifa_en(seg, vf, equipos):
            return "Primer gol: visita"
        return None
    if fam == "btts":
        return "No ambos anotan" if re.search(r"\bno\b", seg) else "Ambos anotan"
    if fam == "goles":
        return _sel_linea(seg, "goles", GOLES, GOLES)
    if fam == "tarj":
        return _sel_linea(seg, "tarjetas", TARJETAS_O, TARJETAS_U)
    if fam == "corn":
        return _sel_linea(seg, "córners", CORNERS, CORNERS)
    return None


def _detectar_partidos(t: str, equipos, tipos_pos):
    apar = []
    for nn, fifa, _d in equipos:
        s = 0
        while True:
            p = t.find(nn, s)
            if p < 0:
                break
            apar.append((p, p + len(nn), fifa))
            s = p + 1
    apar.sort()
    dedup = []
    for p0, e0, f0 in apar:
        if dedup and dedup[-1][2] == f0 and p0 < dedup[-1][1]:
            if e0 > dedup[-1][1]:
                dedup[-1] = (dedup[-1][0], e0, f0)
            continue
        dedup.append((p0, e0, f0))
    apar = dedup
    partidos = []
    i = 0
    while i < len(apar) - 1:
        _p0, e0, f0 = apar[i]
        p1, e1, f1 = apar[i + 1]
        hay_tipo = any(e0 <= tp < p1 for tp in tipos_pos)
        if f1 != f0 and (p1 - e0) < 45 and not hay_tipo:
            partidos.append((apar[i][0], e1, f0, f1))
            i += 2
        else:
            i += 1
    return partidos


def _decimales_cuota(t: str):
    return [(float(m.group(1).replace(",", ".")), m.start())
            for m in re.finditer(r"(?<!\d)(\d{1,2}[.,]\d{2})(?!\d)", t)]


def cuota_total(texto: str):
    t = _norm(texto)
    dec = _decimales_cuota(t)
    if not dec:
        return None
    m = re.search(r"combinada", t)
    if m:
        post = [v for v, p in dec if p > m.start()]
        if post:
            return post[0]
    return dec[0][0]


def _cuota_item(t: str, pos_ini: int):
    dec = [v for v, p in _decimales_cuota(t) if pos_ini - 70 <= p < pos_ini and 1.01 <= v <= 100]
    return dec[-1] if dec else None


def analizar_multi(texto: str, equipos):
    t = _norm(texto)
    disp_de = {}
    for nn, fifa, disp in equipos:
        disp_de.setdefault(fifa, disp)

    ocur = []
    for kw, fam in TIPOS_MERCADO:
        s = 0
        while True:
            p = t.find(kw, s)
            if p < 0:
                break
            ocur.append((p, p + len(kw), fam))
            s = p + 1
    ocur.sort()
    partidos = _detectar_partidos(t, equipos, [o[0] for o in ocur])

    out, prev = [], 0
    for p0, p1, fam in ocur:
        simple = next((pp for pp in partidos if 0 <= pp[0] - p1 < 30), None)
        if simple:
            lf, vf, pos_ini = simple[2], simple[3], simple[0]
        else:
            antes = [pp for pp in partidos if pp[1] <= p0]
            if not antes:
                prev = p1
                continue
            bb = max(antes, key=lambda pp: pp[1])
            lf, vf, pos_ini = bb[2], bb[3], bb[0]
        mercado = _mercado_seg(t[prev:p0], fam, lf, vf, equipos)
        if mercado:
            out.append(((lf, disp_de.get(lf, lf)), (vf, disp_de.get(vf, vf)), mercado, _cuota_item(t, pos_ini)))
        prev = p1
    return out
