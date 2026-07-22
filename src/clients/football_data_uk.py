from __future__ import annotations

import time
from pathlib import Path

import httpx
import pandas as pd

DIRECTO = "https://www.football-data.co.uk/mmz4281/{ss}/{div}.csv"
ARCHIVO = "https://web.archive.org/web/{ts}id_/https://www.football-data.co.uk/mmz4281/{ss}/{div}.csv"
DIRECTO_EXTRA = "https://www.football-data.co.uk/new/{pais}.csv"
ARCHIVO_EXTRA = "https://web.archive.org/web/{ts}id_/https://www.football-data.co.uk/new/{pais}.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _temporada_corta(temporada: str) -> str:
    ini, fin = temporada.split("-")
    return ini[-2:] + fin


class FootballDataUk:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _es_csv(contenido: bytes) -> bool:
        inicio = contenido[:200].lstrip(b"\xef\xbb\xbf").lstrip()
        return inicio.startswith(b"Div,") and b"HomeTeam" in contenido[:400]

    @staticmethod
    def _es_csv_extra(contenido: bytes) -> bool:
        inicio = contenido[:200].lstrip(b"\xef\xbb\xbf").lstrip()
        return inicio.startswith(b"Country,League,Season")

    @staticmethod
    def _get_reintentos(url: str, params: dict | None = None, intentos: int = 4) -> httpx.Response:
        ultimo: Exception | None = None
        for i in range(intentos):
            try:
                r = httpx.get(url, params=params, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
                r.raise_for_status()
                return r
            except httpx.HTTPError as exc:
                ultimo = exc
                time.sleep(3.0 * (i + 1))
        raise RuntimeError(f"sin respuesta de {url}: {ultimo}")

    def _capturas_archivo(self, ss: str, div: str) -> list[str]:
        r = self._get_reintentos(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": f"football-data.co.uk/mmz4281/{ss}/{div}.csv",
                "output": "json",
                "filter": ["statuscode:200", "mimetype:text/csv"],
                "limit": "-4",
            },
        )
        filas = r.json()
        return [f[1] for f in filas[1:]][::-1]

    def _descargar(self, ss: str, div: str, temporada: str) -> bytes:
        try:
            r = httpx.get(DIRECTO.format(ss=ss, div=div), headers={"User-Agent": UA}, timeout=8, follow_redirects=False)
            if r.status_code == 200 and self._es_csv(r.content):
                return r.content
        except httpx.HTTPError:
            pass
        esperado = 306 if div == "D1" else 380
        mejor: bytes | None = None
        ultimo: Exception | None = None
        for ts in self._capturas_archivo(ss, div):
            try:
                time.sleep(2.0)
                r = self._get_reintentos(ARCHIVO.format(ts=ts, ss=ss, div=div))
            except RuntimeError as exc:
                ultimo = exc
                continue
            if not self._es_csv(r.content):
                continue
            if mejor is None or r.content.count(b"\n") > mejor.count(b"\n"):
                mejor = r.content
            if mejor.count(b"\n") >= esperado:
                return mejor
        if mejor is not None:
            return mejor
        raise RuntimeError(f"football-data.co.uk {div} {temporada}: sin CSV válido ni directo ni en archive.org ({ultimo})")

    def temporada(self, div: str, temporada: str, ttl: float = -1) -> pd.DataFrame:
        ss = _temporada_corta(temporada)
        destino = self._cache_dir / f"{div}_{ss}.csv"
        cacheado = destino.exists() and self._es_csv(destino.read_bytes())
        if not cacheado or (ttl >= 0 and time.time() - destino.stat().st_mtime > ttl):
            destino.write_bytes(self._descargar(ss, div, temporada))
        df = pd.read_csv(destino, encoding="utf-8-sig", encoding_errors="replace", on_bad_lines="skip")
        return df.dropna(subset=["HomeTeam", "AwayTeam"])

    def _capturas_extra(self, pais: str) -> list[str]:
        r = self._get_reintentos(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": f"football-data.co.uk/new/{pais}.csv",
                "output": "json",
                "filter": ["statuscode:200", "mimetype:text/csv"],
                "limit": "-3",
            },
        )
        filas = r.json()
        return [f[1] for f in filas[1:]][::-1]

    def _descargar_extra(self, pais: str) -> bytes:
        try:
            r = httpx.get(DIRECTO_EXTRA.format(pais=pais), headers={"User-Agent": UA}, timeout=8, follow_redirects=False)
            if r.status_code == 200 and self._es_csv_extra(r.content):
                return r.content
        except httpx.HTTPError:
            pass
        mejor: bytes | None = None
        ultimo: Exception | None = None
        for ts in self._capturas_extra(pais):
            try:
                time.sleep(2.0)
                r = self._get_reintentos(ARCHIVO_EXTRA.format(ts=ts, pais=pais))
            except RuntimeError as exc:
                ultimo = exc
                continue
            if not self._es_csv_extra(r.content):
                continue
            if mejor is None or r.content.count(b"\n") > mejor.count(b"\n"):
                mejor = r.content
        if mejor is not None:
            return mejor
        raise RuntimeError(f"football-data.co.uk/new/{pais}.csv: sin CSV válido ni directo ni en archive.org ({ultimo})")

    def extra(self, pais: str, ttl: float = -1) -> pd.DataFrame:
        destino = self._cache_dir / f"extra_{pais}.csv"
        cacheado = destino.exists() and self._es_csv_extra(destino.read_bytes())
        if not cacheado or (ttl >= 0 and time.time() - destino.stat().st_mtime > ttl):
            destino.write_bytes(self._descargar_extra(pais))
        df = pd.read_csv(destino, encoding="utf-8-sig", encoding_errors="replace", on_bad_lines="skip")
        return df.dropna(subset=["Home", "Away"])
