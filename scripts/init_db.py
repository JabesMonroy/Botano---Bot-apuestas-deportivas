from __future__ import annotations

from src.config import load_config
from src.db.database import init_db


def main() -> None:
    cfg = load_config()
    init_db(cfg.db_path)
    print(f"DB inicializada en {cfg.db_path}")


if __name__ == "__main__":
    main()
