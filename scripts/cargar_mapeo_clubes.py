from __future__ import annotations

import difflib
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.clients.football_data import FootballData
from src.clients.odds_api import OddsApi
from src.config import load_config
from src.db.database import connect
from src.ligas import LIGAS, registrar as registrar_ligas

UMBRAL_MATCH = 0.62

RUIDO = (
    "FC|AFC|CF|SC|CFC|SSC|AC|AS|US|SV|VfB|VfL|RC|RCD|CA|UD|BC|OSC|SCO"
    "|Club|de|Real|Balompie|Calcio|1\\.|07|1899|1901|1907|1909|1913|29|05|04"
)

OVERRIDES_ODDS = {
    "Stade Brestois 29": "Brest",
    "Olympique Lyonnais": "Lyon",
    "Stade Rennais FC 1901": "Rennes",
    "Racing Club de Lens": "RC Lens",
}

OVERRIDES_HIST = {
    "FC Internazionale Milano": "Inter",
    "Paris Saint-Germain FC": "Paris SG",
    "Racing Club de Lens": "Lens",
    "Deportivo Alavés": "Alaves",
    "Athletic Club": "Ath Bilbao",
    "Rayo Vallecano de Madrid": "Vallecano",
    "Borussia Mönchengladbach": "M'gladbach",
    "Brighton & Hove Albion FC": "Brighton",
    "Stade Brestois 29": "Brest",
    "Stade Rennais FC 1901": "Rennes",
    "Olympique Lyonnais": "Lyon",
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    t = t.replace("&", " and ")
    t = re.sub(rf"\b({RUIDO})\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[.\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def _mejor_match(nombre_fd: str, candidatos: list[str], overrides: dict[str, str] = OVERRIDES_ODDS) -> str | None:
    if nombre_fd in overrides and overrides[nombre_fd] in candidatos:
        return overrides[nombre_fd]
    n = _norm(nombre_fd)
    mejor, mejor_score = None, 0.0
    for c in candidatos:
        score = difflib.SequenceMatcher(None, n, _norm(c)).ratio()
        if score > mejor_score:
            mejor, mejor_score = c, score
    return mejor if mejor_score >= UMBRAL_MATCH else None


def _migrar(conn: sqlite3.Connection) -> None:
    schema = Path(__file__).resolve().parent.parent / "src" / "db" / "schema_clubes.sql"
    conn.executescript(schema.read_text(encoding="utf-8"))
    columnas = (
        ("equipos", "liga_id", "INTEGER"),
        ("equipos", "fd_uk_nombre", "TEXT"),
        ("partidos", "liga_id", "INTEGER"),
        ("ligas", "fd_org", "TEXT"),
    )
    for tabla, col, tipo in columnas:
        try:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def _codigo_unico(conn: sqlite3.Connection, tla: str, fd_id: int) -> str:
    candidato = tla
    sufijo = 2
    while True:
        fila = conn.execute("SELECT football_data_id FROM equipos WHERE fifa_code=?", (candidato,)).fetchone()
        if fila is None or fila["football_data_id"] == fd_id:
            return candidato
        candidato = f"{tla}{sufijo}"
        sufijo += 1


def _equipos_desde_calendario(fd: FootballData, codigo_fd: str) -> dict[int, dict]:
    data = fd.matches(codigo_fd, ttl=21600)
    equipos: dict[int, dict] = {}
    for m in data.get("matches", []):
        for lado in ("homeTeam", "awayTeam"):
            t = m.get(lado) or {}
            if t.get("id"):
                equipos[t["id"]] = t
    return equipos


def _mapear_liga(conn: sqlite3.Connection, fd: FootballData, odds: OddsApi, liga_id: int, liga) -> None:
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    equipos = _equipos_desde_calendario(fd, liga.fd_org)
    if not equipos:
        print(f"{liga.nombre}: sin calendario todavía en football-data.org")
        return
    for t in equipos.values():
        codigo = _codigo_unico(conn, t.get("tla") or f"E{t['id']}", t["id"])
        conn.execute(
            "INSERT INTO equipos (fifa_code, nombre, football_data_id, football_data_name, liga_id, odds_api_name, actualizado) "
            "VALUES (?, ?, ?, ?, ?, '', ?) "
            "ON CONFLICT(football_data_id) DO UPDATE SET "
            "nombre=excluded.nombre, football_data_name=excluded.football_data_name, "
            "liga_id=COALESCE(equipos.liga_id, excluded.liga_id), actualizado=excluded.actualizado",
            (codigo, t.get("shortName") or t.get("name"), t["id"], t.get("name"), liga_id, ahora),
        )
        equipo_id = conn.execute("SELECT id FROM equipos WHERE football_data_id=?", (t["id"],)).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO equipos_competicion (equipo_id, liga_id) VALUES (?, ?)", (equipo_id, liga_id)
        )
    conn.commit()

    eventos = []
    if liga.odds_api:
        try:
            eventos = odds.odds(liga.odds_api, markets="h2h", bookmakers="pinnacle", ttl=3600)
        except Exception as exc:
            print(f"{liga.nombre}: The Odds API falló ({exc}); sin cruce de nombres")
    candidatos = sorted({e[c] for e in eventos for c in ("home_team", "away_team")})

    filas = conn.execute("SELECT id, football_data_name FROM equipos WHERE liga_id=?", (liga_id,)).fetchall()
    emparejados, sin_cruce = 0, []
    for f in filas:
        m = _mejor_match(f["football_data_name"], candidatos)
        if m:
            conn.execute("UPDATE equipos SET odds_api_name=? WHERE id=?", (m, f["id"]))
            emparejados += 1
        else:
            sin_cruce.append(f["football_data_name"])
    conn.commit()
    print(f"{liga.nombre}: {len(equipos)} equipos | {len(candidatos)} nombres en Odds API | {emparejados} cruzados")
    if sin_cruce:
        print(f"  sin cruzar en Odds API ({len(sin_cruce)}, quedan sin cuota hasta que se publique su partido o se agregue un override): {', '.join(sin_cruce)}")

    nombres_hist = sorted({
        r[0]
        for r in conn.execute(
            "SELECT local FROM partidos_club pc JOIN ligas l ON pc.liga_id=l.id WHERE l.codigo=? "
            "UNION SELECT visita FROM partidos_club pc JOIN ligas l ON pc.liga_id=l.id WHERE l.codigo=?",
            (liga.codigo, liga.codigo),
        )
    })
    if nombres_hist:
        sin_hist = []
        for f in filas:
            m = _mejor_match(f["football_data_name"], nombres_hist, overrides=OVERRIDES_HIST)
            if m:
                conn.execute("UPDATE equipos SET fd_uk_nombre=? WHERE id=?", (m, f["id"]))
            else:
                sin_hist.append(f["football_data_name"])
        conn.commit()
        if sin_hist:
            print(f"  sin histórico football-data.co.uk ({len(sin_hist)}, recién ascendidos o sin backtest): {', '.join(sin_hist)}")


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    _migrar(conn)
    liga_id = registrar_ligas(conn)

    fd = FootballData(cfg.football_data_key, cfg.cache_dir / "football_data")
    odds = OddsApi(cfg.odds_api_key, cfg.cache_dir / "odds_api")
    try:
        for liga in LIGAS:
            if not liga.fd_org:
                print(f"{liga.nombre}: sin football-data.org (usa su propio script de ingesta)")
                continue
            _mapear_liga(conn, fd, odds, liga_id[liga.codigo], liga)
    finally:
        fd.close()
        odds.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
