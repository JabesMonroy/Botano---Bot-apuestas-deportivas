from __future__ import annotations

from src.apuestas import actualizar, resumen
from src.config import load_config
from src.db import turso
from src.db.database import connect


def main() -> int:
    cfg = load_config()
    conn_partidos = connect(cfg.db_path)
    conn_apuestas = turso.connect(cfg)
    n = actualizar(conn_apuestas, conn_partidos)
    print(f"apuestas actualizadas (cierre/CLV/resultado): {n}\n")
    resumen(conn_apuestas)
    conn_partidos.close()
    conn_apuestas.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
