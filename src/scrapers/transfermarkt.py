from __future__ import annotations

import re
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

URL = "https://www.transfermarkt.com/weltmeisterschaft/teilnehmer/pokalwettbewerb/FIWC/saison_id/2025"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _num(txt: str) -> float | None:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)(bn|m|k|Th\.)", txt)
    if not m:
        return None
    x = float(m.group(1))
    return x * 1000 if m.group(2) == "bn" else (x if m.group(2) == "m" else x / 1000)


class Transfermarkt:
    def __init__(self, cache_dir: Path, ttl: float = 86400) -> None:
        self._cache = cache_dir / "transfermarkt"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl

    def _html(self) -> str:
        destino = self._cache / "participantes.html"
        if destino.exists() and time.time() - destino.stat().st_mtime < self._ttl:
            return destino.read_text(encoding="utf-8")
        r = httpx.get(URL, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=25, follow_redirects=True)
        r.raise_for_status()
        destino.write_text(r.text, encoding="utf-8")
        return r.text

    def valores(self) -> dict[str, float]:
        soup = BeautifulSoup(self._html(), "lxml")
        out: dict[str, float] = {}
        for tr in soup.select("table.items > tbody > tr"):
            nombre = ""
            for a in tr.select('a[href*="/startseite/verein/"]'):
                if a.get_text(strip=True):
                    nombre = a.get_text(strip=True)
                    break
            if not nombre:
                continue
            euros = [v for v in (_num(td.get_text()) for td in tr.select("td") if "€" in td.get_text()) if v]
            if euros:
                out[nombre] = max(euros)
        return out
