from __future__ import annotations

import sqlite3
import unicodedata

from src.config import load_config
from src.db.database import connect
from src.mapeo import cargar_csv
from src.scrapers.footystats import Footystats

OVERRIDES = {"USA": ("USA",), "KOR": ("South Korea",), "IRN": ("Iran",), "COD": ("DR Congo",)}
COLUMNAS = ("corners_favor REAL", "tarjetas_partido REAL", "xg_fs REAL", "xga_fs REAL")


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def main() -> int:
    cfg = load_config()
    idx = {_norm(p): s for p, s in Footystats(cfg.cache_dir).stats().items()}

    equipos = cargar_csv(cfg.data_dir / "referencia" / "equipos_mundial2026.csv")
    asignados = {}
    for e in equipos:
        for n in (e.odds_api_name, e.eloratings_name, e.football_data_name, e.nombre, *OVERRIDES.get(e.fifa_code, ())):
            if n and _norm(n) in idx:
                asignados[e.fifa_code] = idx[_norm(n)]
                break

    conn = connect(cfg.db_path)
    for col in COLUMNAS:
        try:
            conn.execute(f"ALTER TABLE equipos ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    with conn:
        for fifa, s in asignados.items():
            conn.execute(
                "UPDATE equipos SET corners_favor=?, tarjetas_partido=?, xg_fs=?, xga_fs=? WHERE fifa_code=?",
                (s["corners"], s["tarjetas_partido"], s["xg"], s["xga"], fifa),
            )
    sin = [e.fifa_code for e in equipos if e.fifa_code not in asignados]
    conn.close()

    print(f"estadisticas (corners/tarjetas/xG) asignadas: {len(asignados)}/{len(equipos)} (Footystats)")
    if sin:
        print("sin datos (conciliar nombre):", ", ".join(sin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
