from __future__ import annotations

from src.clients.football_data import FootballData
from src.config import load_config
from src.db.database import connect
from src.ingesta import ingestar_standings


def main() -> None:
    cfg = load_config()
    conn = connect(cfg.db_path)
    fd = FootballData(cfg.football_data_key, cfg.cache_dir / "football_data")
    try:
        n = ingestar_standings(conn, fd)
    finally:
        fd.close()
        conn.close()
    print(f"{n} filas de standings ingestadas/actualizadas")


if __name__ == "__main__":
    main()
