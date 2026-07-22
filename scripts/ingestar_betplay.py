from __future__ import annotations

import sqlite3
import sys
import unicodedata
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.clients.api_football import ApiFootball
from src.config import load_config
from src.db.database import connect
from src.ligas import LIGAS, registrar as registrar_ligas

TEMPORADAS = (2022, 2023, 2024)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return t.strip().lower()


def _migrar(conn: sqlite3.Connection) -> None:
    schema = Path(__file__).resolve().parent.parent / "src" / "db" / "schema_clubes.sql"
    conn.executescript(schema.read_text(encoding="utf-8"))
    for tabla, col, tipo in (("equipos", "liga_id", "INTEGER"), ("partidos", "liga_id", "INTEGER"), ("ligas", "fd_org", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def _codigo_unico(conn: sqlite3.Connection, base: str, api_id: int) -> str:
    candidato = base
    sufijo = 2
    while True:
        fila = conn.execute("SELECT api_football_id FROM equipos WHERE fifa_code=?", (candidato,)).fetchone()
        if fila is None or fila["api_football_id"] == api_id:
            return candidato
        candidato = f"{base}{sufijo}"
        sufijo += 1


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    _migrar(conn)
    liga_id = registrar_ligas(conn)
    liga = next(l for l in LIGAS if l.codigo == "CO1")
    cod_liga = liga_id[liga.codigo]

    af = ApiFootball(cfg.api_football_key, cfg.api_football_host, cfg.cache_dir / "api_football")
    equipos: dict[int, str] = {}
    logos: dict[int, str | None] = {}
    filas_totales = []
    for temporada in TEMPORADAS:
        data = af.fixtures(league=liga.api_football_id, season=temporada)
        fixtures = data.get("response", [])
        if data.get("errors"):
            print(f"  temporada {temporada}: {data['errors']}")
            continue
        for fx in fixtures:
            home, away = fx["teams"]["home"], fx["teams"]["away"]
            equipos[home["id"]] = home["name"]
            equipos[away["id"]] = away["name"]
            logos[home["id"]] = home.get("logo")
            logos[away["id"]] = away.get("logo")
            gh, ga = fx["goals"]["home"], fx["goals"]["away"]
            if gh is None or ga is None:
                continue
            semestre = "C" if "clausura" in (fx["league"].get("round") or "").lower() else "A"
            filas_totales.append((f"{temporada}-{semestre}", fx["fixture"]["date"][:10], home["id"], away["id"], gh, ga))
        print(f"  temporada {temporada}: {len(fixtures)} partidos")
    af.close()

    for api_id, nombre in equipos.items():
        base = _norm(nombre).split()[0][:3].upper() or "EQU"
        codigo = _codigo_unico(conn, base, api_id)
        conn.execute(
            "INSERT INTO equipos (fifa_code, nombre, api_football_id, liga_id, odds_api_name, escudo_url, actualizado) "
            "VALUES (?, ?, ?, ?, '', ?, datetime('now')) "
            "ON CONFLICT(api_football_id) DO UPDATE SET nombre=excluded.nombre, "
            "liga_id=COALESCE(equipos.liga_id, excluded.liga_id), "
            "escudo_url=COALESCE(equipos.escudo_url, excluded.escudo_url)",
            (codigo, nombre, api_id, cod_liga, logos.get(api_id)),
        )
        equipo_id = conn.execute("SELECT id FROM equipos WHERE api_football_id=?", (api_id,)).fetchone()["id"]
        conn.execute("INSERT OR IGNORE INTO equipos_competicion (equipo_id, liga_id) VALUES (?, ?)", (equipo_id, cod_liga))
    conn.commit()

    id_a_nombre = {api_id: nombre for api_id, nombre in equipos.items()}
    columnas = (
        "liga_id, temporada, fecha, local, visita, goles_local, goles_visita, "
        + "tiros_local, tiros_visita, tiros_arco_local, tiros_arco_visita, corners_local, corners_visita, "
        + "faltas_local, faltas_visita, amarillas_local, amarillas_visita, rojas_local, rojas_visita, "
        + "ps_h, ps_d, ps_a, psc_h, psc_d, psc_a, p_over25, p_under25, pc_over25, pc_under25, "
        + "ah_linea, ahc_linea, pcah_h, pcah_a, xg_local, xg_visita"
    )
    total_columnas = len(columnas.split(","))
    marcas = ",".join("?" * total_columnas)
    registros = [
        (cod_liga, str(temporada), fecha, id_a_nombre[h], id_a_nombre[a], gh, ga) + (None,) * (total_columnas - 7)
        for temporada, fecha, h, a, gh, ga in filas_totales
    ]
    with conn:
        conn.execute("DELETE FROM partidos_club WHERE liga_id=?", (cod_liga,))
        conn.executemany(f"INSERT OR IGNORE INTO partidos_club ({columnas}) VALUES ({marcas})", registros)
    conn.close()
    print(f"\n{liga.nombre}: {len(equipos)} equipos | {len(registros)} partidos jugados (2022-2024, sin cuotas ni estadísticas de partido)")
    print("Aviso: API-Football free no da temporadas 2025/2026 (plan gratis limitado a 2022-2024) — sin calendario en vivo para esta competición todavía.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
