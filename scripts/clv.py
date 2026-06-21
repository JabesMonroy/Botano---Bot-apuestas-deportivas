from __future__ import annotations

from src.apuestas import actualizar, resumen
from src.config import load_config
from src.db.database import connect


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    n = actualizar(conn)
    print(f"apuestas actualizadas (cierre/CLV/resultado): {n}\n")
    resumen(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
