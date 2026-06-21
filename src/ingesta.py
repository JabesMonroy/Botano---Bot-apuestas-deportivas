from __future__ import annotations

import sqlite3
import unicodedata
from datetime import datetime, timezone

from src.clients.football_data import FootballData
from src.clients.odds_api import OddsApi

SPORT = "soccer_fifa_world_cup"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower()


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def ingestar_partidos(conn: sqlite3.Connection, fd: FootballData) -> int:
    por_fd = {
        r["football_data_id"]: r["id"]
        for r in conn.execute("SELECT id, football_data_id FROM equipos WHERE football_data_id IS NOT NULL")
    }
    data = fd.matches()
    ahora = _ahora()
    filas = []
    for m in data.get("matches", []):
        local = por_fd.get((m.get("homeTeam") or {}).get("id"))
        visita = por_fd.get((m.get("awayTeam") or {}).get("id"))
        if local is None or visita is None:
            continue
        filas.append(
            (
                m.get("id"),
                m.get("utcDate"),
                local,
                visita,
                m.get("stage"),
                m.get("group"),
                m.get("status"),
                ahora,
            )
        )
    sql = """
        INSERT INTO partidos (
            football_data_id, fecha, equipo_local_id, equipo_visita_id, fase, grupo, estado, actualizado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(football_data_id) DO UPDATE SET
            fecha = excluded.fecha,
            equipo_local_id = excluded.equipo_local_id,
            equipo_visita_id = excluded.equipo_visita_id,
            fase = excluded.fase,
            grupo = excluded.grupo,
            estado = excluded.estado,
            actualizado = excluded.actualizado
    """
    with conn:
        conn.executemany(sql, filas)
    return len(filas)


def _buscar_partido(conn: sqlite3.Connection, eq_a: int, eq_b: int, commence: str | None) -> int | None:
    rows = conn.execute(
        "SELECT id, fecha FROM partidos WHERE (equipo_local_id=? AND equipo_visita_id=?) "
        "OR (equipo_local_id=? AND equipo_visita_id=?)",
        (eq_a, eq_b, eq_b, eq_a),
    ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]["id"]
    objetivo = _parse(commence)
    if objetivo is None:
        return rows[0]["id"]
    mejor, mejor_diff = rows[0]["id"], None
    for r in rows:
        d = _parse(r["fecha"])
        if d is None:
            continue
        diff = abs((d - objetivo).total_seconds())
        if mejor_diff is None or diff < mejor_diff:
            mejor, mejor_diff = r["id"], diff
    return mejor


def ingestar_cuotas(conn: sqlite3.Connection, odds: OddsApi, casa: str = "pinnacle") -> int:
    por_odds = {
        _norm(r["odds_api_name"]): r
        for r in conn.execute("SELECT id, fifa_code, odds_api_name FROM equipos WHERE odds_api_name != ''")
    }
    eventos = odds.odds(SPORT, markets="h2h", bookmakers=casa)
    ahora = _ahora()
    insertados = 0
    with conn:
        for ev in eventos:
            home = por_odds.get(_norm(ev.get("home_team", "")))
            away = por_odds.get(_norm(ev.get("away_team", "")))
            if not home or not away:
                continue
            partido = _buscar_partido(conn, home["id"], away["id"], ev.get("commence_time"))
            if partido is None:
                continue
            book = next((b for b in ev.get("bookmakers", []) if b.get("key") == casa), None)
            if book is None:
                continue
            h2h = next((mk for mk in book.get("markets", []) if mk.get("key") == "h2h"), None)
            if h2h is None:
                continue
            conn.execute(
                "DELETE FROM cuotas WHERE partido_id=? AND casa=? AND mercado='1X2'",
                (partido, casa),
            )
            for o in h2h.get("outcomes", []):
                nombre = _norm(o.get("name", ""))
                if nombre == "draw":
                    seleccion = "X"
                elif nombre == _norm(ev.get("home_team", "")):
                    seleccion = home["fifa_code"]
                elif nombre == _norm(ev.get("away_team", "")):
                    seleccion = away["fifa_code"]
                else:
                    continue
                conn.execute(
                    "INSERT INTO cuotas (partido_id, casa, mercado, seleccion, cuota, capturado) "
                    "VALUES (?, ?, '1X2', ?, ?, ?)",
                    (partido, casa, seleccion, o.get("price"), ahora),
                )
                insertados += 1
    return insertados
