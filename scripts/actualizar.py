from __future__ import annotations

from src.clients.football_data import FootballData
from src.clients.odds_api import OddsApi
from src.config import load_config
from src.db.database import connect
from src.ingesta import ingestar_cuotas, ingestar_partidos, ingestar_resultados, ingestar_standings


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)

    fd = FootballData(cfg.football_data_key, cfg.cache_dir / "football_data")
    try:
        np_ = ingestar_partidos(conn, fd)
        nr = ingestar_resultados(conn, fd)
        ns = ingestar_standings(conn, fd)
    finally:
        fd.close()

    odds = OddsApi(cfg.odds_api_key, cfg.cache_dir / "odds_api")
    try:
        nc = ingestar_cuotas(conn, odds)
    finally:
        odds.close()
    conn.close()

    print(f"partidos {np_} | resultados {nr} | standings {ns} | cuotas Pinnacle {nc}")
    print("siguiente: scripts.clv (actualizar CLV/resultados) y scripts.generar_reporte LOCAL VISITA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
