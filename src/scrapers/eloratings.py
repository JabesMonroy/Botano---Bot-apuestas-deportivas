from __future__ import annotations

import time
from pathlib import Path

import httpx

BASE = "https://www.eloratings.net"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class EloRatings:
    def __init__(self, cache_dir: Path, ttl: float = 86400) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _fetch(self, archivo: str) -> str:
        destino = self._cache_dir / archivo
        if destino.exists() and time.time() - destino.stat().st_mtime < self._ttl:
            return destino.read_text(encoding="utf-8")
        r = httpx.get(f"{BASE}/{archivo}", headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
        r.raise_for_status()
        destino.write_text(r.text, encoding="utf-8")
        return r.text

    def _nombres(self) -> dict[str, list[str]]:
        nombres: dict[str, list[str]] = {}
        for linea in self._fetch("en.teams.tsv").splitlines():
            campos = linea.split("\t")
            if len(campos) < 2 or "_" in campos[0]:
                continue
            nombres[campos[0]] = [c for c in campos[1:] if c]
        return nombres

    def ratings(self) -> list[tuple[str, str, int, list[str]]]:
        nombres = self._nombres()
        salida: list[tuple[str, str, int, list[str]]] = []
        for linea in self._fetch("World.tsv").splitlines():
            campos = linea.split("\t")
            if len(campos) < 4 or not campos[3].isdigit():
                continue
            code = campos[2]
            alias = nombres.get(code, [])
            principal = alias[0] if alias else code
            salida.append((code, principal, int(campos[3]), alias))
        return salida
