from __future__ import annotations

import unicodedata

from src.clients.api_football import ApiFootball
from src.config import load_config
from src.db.database import connect
from src.historico import ingestar_historico
from src.mapeo import cargar_csv, guardar_csv

LIGAS = [
    (1, 2022),
    (10, 2022),
    (10, 2023),
    (10, 2024),
    (5, 2022),
    (5, 2024),
    (4, 2024),
    (9, 2024),
    (6, 2023),
    (7, 2023),
    (34, 2023),
    (34, 2024),
    (32, 2023),
    (32, 2024),
]


OVERRIDES = {"TUR": ("Türkiye",)}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def main() -> int:
    cfg = load_config()
    if not cfg.api_football_key:
        print("Falta API_FOOTBALL_KEY en .env")
        return 1

    conn = connect(cfg.db_path)
    api = ApiFootball(cfg.api_football_key, cfg.api_football_host, cfg.cache_dir / "api_football")
    try:
        req0 = api.status()["response"]["requests"]["current"]
        resumen = ingestar_historico(conn, api, LIGAS)
        req1 = api.status()["response"]["requests"]["current"]
    finally:
        api.close()

    print("liga(id, season)            partidos  usados")
    for league, season, nombre, total, usados in resumen:
        print(f"  {str(nombre)[:24]:24} ({league},{season})  {total:5}  {usados:5}")
    total_hist = conn.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
    print(f"requests API-Football consumidas: {req1 - req0} | historico total: {total_hist} partidos")

    idx: dict[str, int] = {}
    for r in conn.execute(
        "SELECT home_api_id id, home_name n FROM historico "
        "UNION SELECT away_api_id, away_name FROM historico"
    ):
        if r["id"] is not None and r["n"]:
            idx.setdefault(_norm(r["n"]), r["id"])

    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    equipos = cargar_csv(csv_path)
    emparejados = 0
    for e in equipos:
        candidatos = (e.odds_api_name, e.eloratings_name, e.football_data_name, e.nombre, *OVERRIDES.get(e.fifa_code, ()))
        for n in candidatos:
            if n and _norm(n) in idx:
                e.api_football_id = idx[_norm(n)]
                emparejados += 1
                break
    guardar_csv(csv_path, equipos)
    with conn:
        for e in equipos:
            if e.api_football_id:
                conn.execute("UPDATE equipos SET api_football_id=? WHERE fifa_code=?", (e.api_football_id, e.fifa_code))
    sin = [e.fifa_code for e in equipos if not e.api_football_id]
    conn.close()

    print(f"api_football_id asignado: {emparejados} / {len(equipos)}")
    if sin:
        print("sin api_football_id:", ", ".join(sin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
