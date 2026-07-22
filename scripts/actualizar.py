from __future__ import annotations

from src.clients.football_data import FootballData
from src.clients.odds_api import OddsApi
from src.config import Config, load_config
from src.db.database import connect
from src.ingesta import ingestar_cuotas, ingestar_partidos, ingestar_resultados, ingestar_standings


def actualizar(cfg: Config) -> dict:
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

    return {"partidos": np_, "resultados": nr, "standings": ns, "cuotas": nc}


def main() -> int:
    r = actualizar(load_config())
    print(
        f"partidos {r['partidos']} | resultados {r['resultados']} | standings {r['standings']} | "
        f"cuotas Pinnacle 1X2 {r['cuotas']['1x2']} · totals {r['cuotas']['totals']} · btts {r['cuotas']['btts']}"
    )
    print("siguiente: scripts.clv (actualizar CLV/resultados) y scripts.generar_reporte LOCAL VISITA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
