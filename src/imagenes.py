from __future__ import annotations

from io import BytesIO

import httpx
from PIL import Image


def color_dominante(url: str, timeout: float = 10.0) -> str | None:
    if not url:
        return None
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception:
        return None

    img.thumbnail((64, 64))
    conteo: dict[tuple[int, int, int], int] = {}
    for r, g, b, a in img.getdata():
        if a < 128:
            continue
        if r > 235 and g > 235 and b > 235:
            continue
        if r < 20 and g < 20 and b < 20:
            continue
        clave = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
        conteo[clave] = conteo.get(clave, 0) + 1
    if not conteo:
        return None
    r, g, b = max(conteo, key=conteo.get)
    return f"#{r:02x}{g:02x}{b:02x}"
