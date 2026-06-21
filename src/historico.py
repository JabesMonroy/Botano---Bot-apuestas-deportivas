from __future__ import annotations

import sqlite3

from src.clients.api_football import ApiFootball

FINALIZADO = {"FT", "AET", "PEN"}


def ingestar_historico(
    conn: sqlite3.Connection, api: ApiFootball, ligas: list[tuple[int, int]]
) -> list[tuple[int, int, str | None, int, int]]:
    filas = []
    resumen = []
    for league, season in ligas:
        data = api.fixtures(league=league, season=season)
        resp = data.get("response", [])
        nombre = resp[0]["league"]["name"] if resp else None
        usados = 0
        for it in resp:
            g = it.get("goals") or {}
            st = ((it.get("fixture") or {}).get("status") or {}).get("short")
            if st not in FINALIZADO or g.get("home") is None or g.get("away") is None:
                continue
            fx, lg, tm = it["fixture"], it["league"], it["teams"]
            filas.append(
                (
                    fx.get("id"),
                    fx.get("date"),
                    lg.get("name"),
                    lg.get("id"),
                    lg.get("season"),
                    tm["home"].get("id"),
                    tm["home"].get("name"),
                    tm["away"].get("id"),
                    tm["away"].get("name"),
                    g.get("home"),
                    g.get("away"),
                )
            )
            usados += 1
        resumen.append((league, season, nombre, len(resp), usados))
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO historico "
            "(api_fixture_id, fecha, liga, liga_id, season, home_api_id, home_name, "
            "away_api_id, away_name, goles_home, goles_away) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            filas,
        )
    return resumen
