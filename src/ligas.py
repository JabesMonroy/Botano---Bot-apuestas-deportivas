from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Liga:
    codigo: str
    nombre: str
    pais: str
    fd_uk: str | None
    understat: str | None
    odds_api: str | None
    fd_org: str | None
    fd_uk_extra: bool = False
    api_football_id: int | None = None
    fuente_calendario: str | None = None

    def __post_init__(self) -> None:
        if self.fuente_calendario is None and self.fd_org:
            object.__setattr__(self, "fuente_calendario", "football-data.org")


LIGAS = [
    Liga("E0", "Premier League", "Inglaterra", "E0", "EPL", "soccer_epl", "PL"),
    Liga("SP1", "La Liga", "España", "SP1", "La_liga", "soccer_spain_la_liga", "PD"),
    Liga("I1", "Serie A", "Italia", "I1", "Serie_A", "soccer_italy_serie_a", "SA"),
    Liga("D1", "Bundesliga", "Alemania", "D1", "Bundesliga", "soccer_germany_bundesliga", "BL1"),
    Liga("F1", "Ligue 1", "Francia", "F1", "Ligue_1", "soccer_france_ligue_one", "FL1"),
    Liga("CL", "Champions League", "Europa", None, None, "soccer_uefa_champs_league", "CL"),
    Liga("BRA", "Brasileirão", "Brasil", "BRA", None, "soccer_brazil_campeonato", "BSA", fd_uk_extra=True),
    Liga("CO1", "Liga BetPlay", "Colombia", None, None, None, None, api_football_id=239, fuente_calendario="API-Football (por fecha)"),
]

POR_CODIGO = {l.codigo: l for l in LIGAS}
POR_FD_ORG = {l.fd_org: l for l in LIGAS if l.fd_org}


def registrar(conn: sqlite3.Connection) -> dict[str, int]:
    for liga in LIGAS:
        conn.execute(
            "INSERT INTO ligas (codigo, nombre, pais, understat, odds_api, fd_org) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre, understat=excluded.understat, "
            "odds_api=excluded.odds_api, fd_org=excluded.fd_org",
            (liga.codigo, liga.nombre, liga.pais, liga.understat, liga.odds_api, liga.fd_org),
        )
    conn.commit()
    return {r["codigo"]: r["id"] for r in conn.execute("SELECT id, codigo FROM ligas")}
