from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
AL_ARCO = {"Goal", "Saved", "Saved to Post"}


def _get_json(url: str, destino: Path, ttl: float = 2592000):
    if destino.exists() and time.time() - destino.stat().st_mtime < ttl:
        return json.loads(destino.read_text(encoding="utf-8"))
    r = httpx.get(url, timeout=40)
    r.raise_for_status()
    destino.write_text(r.text, encoding="utf-8")
    return r.json()


def calibrar_tiros(cache_dir: Path, comp: int = 43, season: int = 106, n_partidos: int = 20) -> dict | None:
    cache = cache_dir / "statsbomb"
    cache.mkdir(parents=True, exist_ok=True)
    matches = _get_json(f"{BASE}/matches/{comp}/{season}.json", cache / f"matches_{comp}_{season}.json")

    tiros = al_arco = goles = 0
    xg = 0.0
    usados = 0
    for m in matches[:n_partidos]:
        try:
            eventos = _get_json(f"{BASE}/events/{m['match_id']}.json", cache / f"events_{m['match_id']}.json")
        except Exception:
            continue
        for e in eventos:
            if e.get("type", {}).get("name") != "Shot":
                continue
            s = e["shot"]
            tiros += 1
            xg += s.get("statsbomb_xg", 0.0)
            outcome = s.get("outcome", {}).get("name")
            if outcome in AL_ARCO:
                al_arco += 1
            if outcome == "Goal":
                goles += 1
        usados += 1

    if tiros == 0:
        return None
    return {
        "xg_por_tiro": round(xg / tiros, 4),
        "ratio_al_arco": round(al_arco / tiros, 4),
        "conversion": round(goles / tiros, 4),
        "n_tiros": tiros,
        "n_partidos": usados,
        "fuente": "StatsBomb Open Data · FIFA World Cup 2022",
    }
