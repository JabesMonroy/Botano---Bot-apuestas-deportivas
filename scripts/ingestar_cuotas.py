from __future__ import annotations

from src.clients.odds_api import OddsApi
from src.config import load_config
from src.db.database import connect
from src.ingesta import ingestar_cuotas


def main() -> None:
    cfg = load_config()
    conn = connect(cfg.db_path)
    odds = OddsApi(cfg.odds_api_key, cfg.cache_dir / "odds_api")
    try:
        n = ingestar_cuotas(conn, odds)
    finally:
        odds.close()
        conn.close()
    print(f"{n} cuotas 1X2 (Pinnacle) ingestadas")


if __name__ == "__main__":
    main()
