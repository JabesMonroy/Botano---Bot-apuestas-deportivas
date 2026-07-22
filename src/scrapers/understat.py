from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "https://understat.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
LIGAS = ("EPL", "La_liga", "Serie_A", "Bundesliga", "Ligue_1", "RFPL")


class Understat:
    def __init__(self, cache_dir: Path, ttl: float = 86400) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _datos(self, liga: str, anio: int) -> dict:
        destino = self._cache_dir / f"{liga}_{anio}.json"
        if destino.exists() and time.time() - destino.stat().st_mtime < self._ttl:
            return json.loads(destino.read_text(encoding="utf-8"))
        ultimo: Exception | None = None
        for intento in range(4):
            try:
                r = httpx.get(
                    f"{BASE}/getLeagueData/{liga}/{anio}",
                    headers={
                        "User-Agent": UA,
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": f"{BASE}/league/{liga}/{anio}",
                    },
                    timeout=30,
                )
                r.raise_for_status()
                break
            except (httpx.HTTPError, OSError) as exc:
                ultimo = exc
                time.sleep(3.0 * (intento + 1))
        else:
            raise RuntimeError(f"understat {liga}/{anio}: {ultimo}")
        datos = r.json()
        if "dates" not in datos:
            raise ValueError(f"understat: respuesta sin 'dates' para {liga}/{anio}")
        destino.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return datos

    def partidos(self, liga: str, anio: int) -> list[dict]:
        salida = []
        for p in self._datos(liga, anio).get("dates", []):
            if not p.get("isResult"):
                continue
            salida.append(
                {
                    "fecha": p["datetime"][:10],
                    "local": p["h"]["title"],
                    "visita": p["a"]["title"],
                    "goles_local": int(p["goals"]["h"]),
                    "goles_visita": int(p["goals"]["a"]),
                    "xg_local": float(p["xG"]["h"]),
                    "xg_visita": float(p["xG"]["a"]),
                }
            )
        return salida
