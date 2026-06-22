from __future__ import annotations

import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

URL = "https://footystats.org/world-cup"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _f(txt: str) -> float | None:
    try:
        return float(txt.replace("%", "").strip())
    except ValueError:
        return None


class Footystats:
    def __init__(self, cache_dir: Path, ttl: float = 86400) -> None:
        self._cache = cache_dir / "footystats"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl

    def _html(self) -> str:
        destino = self._cache / "world-cup.html"
        if destino.exists() and time.time() - destino.stat().st_mtime < self._ttl:
            return destino.read_text(encoding="utf-8")
        r = httpx.get(URL, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=25, follow_redirects=True)
        r.raise_for_status()
        destino.write_text(r.text, encoding="utf-8")
        return r.text

    def stats(self) -> dict[str, dict]:
        soup = BeautifulSoup(self._html(), "lxml")
        tabla = soup.select_one("table")
        headers = [th.get_text(strip=True) for th in tabla.select("thead th")]
        idx = {h: i for i, h in enumerate(headers)}
        out: dict[str, dict] = {}
        for tr in tabla.select("tbody tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(tds) < len(headers) or "Country" not in idx:
                continue
            pais = tds[idx["Country"]]
            partidos = _f(tds[idx["P"]]) if "P" in idx else None
            cards = _f(tds[idx["Cards"]]) if "Cards" in idx else None
            out[pais] = {
                "partidos": partidos,
                "xg": _f(tds[idx["xG"]]) if "xG" in idx else None,
                "xga": _f(tds[idx["xGA"]]) if "xGA" in idx else None,
                "corners": _f(tds[idx["Corners"]]) if "Corners" in idx else None,
                "tarjetas_partido": (cards / partidos) if cards and partidos else None,
            }
        return out
