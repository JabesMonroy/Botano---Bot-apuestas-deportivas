from __future__ import annotations

import sqlite3
import unicodedata
from datetime import datetime, timezone

from src.clients.football_data import FootballData
from src.clients.odds_api import OddsApi

SPORT = "soccer_fifa_world_cup"
WORLD_CUP = FootballData.WORLD_CUP


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


def _grupo(valor: str | None) -> str | None:
    if not valor:
        return None
    return valor.replace("_", " ").split()[-1].upper()


def ingestar_partidos(conn: sqlite3.Connection, fd: FootballData, codigo: int | str = WORLD_CUP, liga_id: int | None = None) -> int:
    por_fd = {
        r["football_data_id"]: r["id"]
        for r in conn.execute("SELECT id, football_data_id FROM equipos WHERE football_data_id IS NOT NULL")
    }
    data = fd.matches(codigo)
    ahora = _ahora()
    filas = []
    for m in data.get("matches", []):
        local = por_fd.get((m.get("homeTeam") or {}).get("id"))
        visita = por_fd.get((m.get("awayTeam") or {}).get("id"))
        if local is None or visita is None:
            continue
        arbitro = ((m.get("referees") or [{}])[0] or {}).get("name")
        filas.append(
            (
                m.get("id"),
                m.get("utcDate"),
                local,
                visita,
                m.get("stage"),
                _grupo(m.get("group")),
                arbitro,
                m.get("status"),
                liga_id,
                ahora,
            )
        )
    sql = """
        INSERT INTO partidos (
            football_data_id, fecha, equipo_local_id, equipo_visita_id, fase, grupo, arbitro, estado, liga_id, actualizado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(football_data_id) DO UPDATE SET
            fecha = excluded.fecha,
            equipo_local_id = excluded.equipo_local_id,
            equipo_visita_id = excluded.equipo_visita_id,
            fase = excluded.fase,
            grupo = excluded.grupo,
            arbitro = excluded.arbitro,
            estado = excluded.estado,
            liga_id = excluded.liga_id,
            actualizado = excluded.actualizado
    """
    with conn:
        conn.executemany(sql, filas)
    return len(filas)


def ingestar_resultados(conn: sqlite3.Connection, fd: FootballData, codigo: int | str = WORLD_CUP) -> int:
    por_match = {
        r["football_data_id"]: r["id"]
        for r in conn.execute("SELECT id, football_data_id FROM partidos WHERE football_data_id IS NOT NULL")
    }
    data = fd.matches(codigo)
    filas = []
    for m in data.get("matches", []):
        pid = por_match.get(m.get("id"))
        if pid is None:
            continue
        ft = ((m.get("score") or {}).get("fullTime")) or {}
        gl, gv = ft.get("home"), ft.get("away")
        if gl is None or gv is None:
            continue
        filas.append((pid, gl, gv, m.get("utcDate")))
    sql = """
        INSERT INTO resultados (partido_id, goles_local, goles_visita, finalizado)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(partido_id) DO UPDATE SET
            goles_local = excluded.goles_local,
            goles_visita = excluded.goles_visita,
            finalizado = excluded.finalizado
    """
    with conn:
        conn.executemany(sql, filas)
    return len(filas)


def ingestar_standings(conn: sqlite3.Connection, fd: FootballData, codigo: int | str = WORLD_CUP, grupo_default: str | None = None) -> int:
    por_fd = {
        r["football_data_id"]: r["id"]
        for r in conn.execute("SELECT id, football_data_id FROM equipos WHERE football_data_id IS NOT NULL")
    }
    st = fd.standings(codigo)
    ahora = _ahora()
    filas = []
    for grupo in st.get("standings", []):
        if grupo.get("type") not in (None, "TOTAL"):
            continue
        g = grupo_default or _grupo(grupo.get("group"))
        for fila in grupo.get("table", []):
            eq = por_fd.get((fila.get("team") or {}).get("id"))
            if eq is None:
                continue
            filas.append(
                (
                    g,
                    eq,
                    fila.get("position"),
                    fila.get("playedGames"),
                    fila.get("won"),
                    fila.get("draw"),
                    fila.get("lost"),
                    fila.get("goalsFor"),
                    fila.get("goalsAgainst"),
                    fila.get("goalDifference"),
                    fila.get("points"),
                    ahora,
                )
            )
    sql = """
        INSERT INTO standings (
            grupo, equipo_id, posicion, jugados, ganados, empatados, perdidos,
            goles_favor, goles_contra, diferencia, puntos, actualizado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(grupo, equipo_id) DO UPDATE SET
            posicion = excluded.posicion,
            jugados = excluded.jugados,
            ganados = excluded.ganados,
            empatados = excluded.empatados,
            perdidos = excluded.perdidos,
            goles_favor = excluded.goles_favor,
            goles_contra = excluded.goles_contra,
            diferencia = excluded.diferencia,
            puntos = excluded.puntos,
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


DIAS_BTTS = 4.0


def _mercado_book(ev: dict, casa: str, clave: str) -> dict | None:
    book = next((b for b in ev.get("bookmakers", []) if b.get("key") == casa), None)
    if book is None:
        return None
    return next((mk for mk in book.get("markets", []) if mk.get("key") == clave), None)


def _guardar_totals(conn: sqlite3.Connection, partido: int, casa: str, mercado: dict, ahora: str) -> int:
    filas = []
    for o in mercado.get("outcomes", []):
        lado = _norm(o.get("name", ""))
        punto = o.get("point")
        if lado not in ("over", "under") or punto is None or o.get("price") is None:
            continue
        filas.append((partido, casa, f"{lado}{punto}", o.get("price"), ahora))
    if not filas:
        return 0
    conn.execute("DELETE FROM cuotas WHERE partido_id=? AND casa=? AND mercado='totals'", (partido, casa))
    conn.executemany(
        "INSERT INTO cuotas (partido_id, casa, mercado, seleccion, cuota, capturado) VALUES (?, ?, 'totals', ?, ?, ?)",
        filas,
    )
    return len(filas)


def _guardar_btts(conn: sqlite3.Connection, partido: int, casa: str, mercado: dict, ahora: str) -> int:
    filas = []
    for o in mercado.get("outcomes", []):
        lado = {"yes": "si", "no": "no"}.get(_norm(o.get("name", "")))
        if lado is None or o.get("price") is None:
            continue
        filas.append((partido, casa, lado, o.get("price"), ahora))
    if not filas:
        return 0
    conn.execute("DELETE FROM cuotas WHERE partido_id=? AND casa=? AND mercado='btts'", (partido, casa))
    conn.executemany(
        "INSERT INTO cuotas (partido_id, casa, mercado, seleccion, cuota, capturado) VALUES (?, ?, 'btts', ?, ?, ?)",
        filas,
    )
    return len(filas)


def ingestar_cuotas(conn: sqlite3.Connection, odds: OddsApi, casa: str = "pinnacle", sport: str = SPORT) -> dict[str, int]:
    por_odds = {
        _norm(r["odds_api_name"]): r
        for r in conn.execute("SELECT id, fifa_code, odds_api_name FROM equipos WHERE odds_api_name != ''")
    }
    eventos = odds.odds(sport, markets="h2h,totals", bookmakers=casa)
    ahora = _ahora()
    conteo = {"1x2": 0, "totals": 0, "btts": 0}
    ahora_dt = datetime.now(timezone.utc)
    with conn:
        for ev in eventos:
            home = por_odds.get(_norm(ev.get("home_team", "")))
            away = por_odds.get(_norm(ev.get("away_team", "")))
            if not home or not away:
                continue
            partido = _buscar_partido(conn, home["id"], away["id"], ev.get("commence_time"))
            if partido is None:
                continue
            h2h = _mercado_book(ev, casa, "h2h")
            if h2h is not None:
                conn.execute("DELETE FROM cuotas WHERE partido_id=? AND casa=? AND mercado='1X2'", (partido, casa))
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
                    conteo["1x2"] += 1

            totals = _mercado_book(ev, casa, "totals")
            if totals is not None:
                conteo["totals"] += _guardar_totals(conn, partido, casa, totals, ahora)

            inicio = _parse(ev.get("commence_time"))
            if inicio and 0 <= (inicio - ahora_dt).total_seconds() <= DIAS_BTTS * 86400 and ev.get("id"):
                try:
                    ev_btts = odds.event_odds(SPORT, ev["id"], markets="btts", bookmakers=casa)
                except Exception:
                    ev_btts = None
                btts = _mercado_book(ev_btts, casa, "btts") if ev_btts else None
                if btts is not None:
                    conteo["btts"] += _guardar_btts(conn, partido, casa, btts, ahora)
    return conteo
