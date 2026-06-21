from __future__ import annotations

from src.config import load_config
from src.db.database import connect
from src.mapeo import cargar_csv, upsert_db


def main() -> None:
    cfg = load_config()
    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    equipos = cargar_csv(csv_path)
    conn = connect(cfg.db_path)
    try:
        n = upsert_db(conn, equipos)
    finally:
        conn.close()
    print(f"{n} equipos cargados/actualizados desde {csv_path.name}")


if __name__ == "__main__":
    main()
