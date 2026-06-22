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


def _intval(txt: str) -> int:
    t = txt.replace(".", "").replace(",", "").strip()
    return int(t) if t.isdigit() else 0


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

    def participantes(self) -> dict[str, tuple[int, float | None]]:
        soup = BeautifulSoup(self._html(), "lxml")
        out: dict[str, tuple[int, float | None]] = {}
        for tr in soup.select("table.items > tbody > tr"):
            nombre, href = "", ""
            for a in tr.select('a[href*="/startseite/verein/"]'):
                if a.get_text(strip=True):
                    nombre, href = a.get_text(strip=True), a.get("href", "")
                    break
            m = re.search(r"/verein/(\d+)", href)
            if not nombre or not m:
                continue
            euros = [v for v in (_num(td.get_text()) for td in tr.select("td") if "€" in td.get_text()) if v]
            out[nombre] = (int(m.group(1)), max(euros) if euros else None)
        return out

    def valores(self) -> dict[str, float]:
        return {n: v for n, (_id, v) in self.participantes().items() if v}

    def _html_kader(self, verein_id: int) -> str:
        destino = self._cache / f"kader_{verein_id}.html"
        if destino.exists() and time.time() - destino.stat().st_mtime < self._ttl:
            return destino.read_text(encoding="utf-8")
        r = httpx.get(
            f"https://www.transfermarkt.com/x/kader/verein/{verein_id}",
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=25,
            follow_redirects=True,
        )
        r.raise_for_status()
        destino.write_text(r.text, encoding="utf-8")
        return r.text

    def _id_arbitro(self, nombre: str) -> str | None:
        r = httpx.get(
            "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche",
            params={"query": nombre},
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=25,
            follow_redirects=True,
        )
        m = re.search(r"/profil/schiedsrichter/(\d+)", r.text)
        return m.group(1) if m else None

    def _html_arbitro(self, arbitro_id: str) -> str:
        destino = self._cache / f"arbitro_{arbitro_id}.html"
        if destino.exists() and time.time() - destino.stat().st_mtime < self._ttl:
            return destino.read_text(encoding="utf-8")
        r = httpx.get(
            f"https://www.transfermarkt.com/x/profil/schiedsrichter/{arbitro_id}",
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=25,
            follow_redirects=True,
        )
        r.raise_for_status()
        destino.write_text(r.text, encoding="utf-8")
        return r.text

    def arbitro_tarjetas(self, nombre: str) -> dict | None:
        arbitro_id = self._id_arbitro(nombre)
        if not arbitro_id:
            return None
        tabla = BeautifulSoup(self._html_arbitro(arbitro_id), "lxml").select_one("table.items")
        if tabla is None:
            return None
        partidos = amarillas = rojas = 0
        for tr in tabla.select("tbody tr"):
            tds = [td.get_text(strip=True) for td in tr.select("td")]
            if len(tds) < 6:
                continue
            partidos += _intval(tds[2])
            amarillas += _intval(tds[3])
            rojas += _intval(tds[5])
        if partidos < 5:
            return None
        return {"partidos": partidos, "amarillas_pp": amarillas / partidos, "rojas_pp": rojas / partidos}

    def kader(self, verein_id: int) -> list[tuple[str, str, float | None]]:
        soup = BeautifulSoup(self._html_kader(verein_id), "lxml")
        out = []
        for tr in soup.select("table.items > tbody > tr"):
            a = tr.select_one("td.hauptlink a") or tr.select_one('a[href*="/profil/spieler/"]')
            if not a or not a.get_text(strip=True):
                continue
            inl = tr.select_one("table.inline-table")
            celdas = [td.get_text(strip=True) for td in inl.select("tr td") if td.get_text(strip=True)] if inl else []
            posicion = celdas[-1] if celdas else ""
            euros = [v for v in (_num(td.get_text()) for td in tr.select("td") if "€" in td.get_text()) if v]
            out.append((a.get_text(strip=True), posicion, euros[-1] if euros else None))
        return out
