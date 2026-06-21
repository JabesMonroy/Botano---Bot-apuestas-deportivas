from __future__ import annotations

import sqlite3
import unicodedata

from src.config import load_config
from src.db.database import connect
from src.mapeo import cargar_csv, guardar_csv
from src.scrapers.transfermarkt import Transfermarkt

OVERRIDES = {
    "IRN": ("IR Iran",),
    "KOR": ("Korea, South",),
    "USA": ("United States",),
    "TUR": ("Turkiye",),
    "COD": ("Democratic Republic of the Congo",),
}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def main() -> int:
    cfg = load_config()
    idx = {_norm(n): par for n, par in Transfermarkt(cfg.cache_dir).participantes().items()}

    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    equipos = cargar_csv(csv_path)
    asignados: dict[str, tuple[int, float | None]] = {}
    for e in equipos:
        candidatos = (e.odds_api_name, e.eloratings_name, e.football_data_name, e.nombre, *OVERRIDES.get(e.fifa_code, ()))
        for n in candidatos:
            if n and _norm(n) in idx:
                asignados[e.fifa_code] = idx[_norm(n)]
                break

    conn = connect(cfg.db_path)
    for col in ("valor_plantilla REAL", "transfermarkt_id INTEGER"):
        try:
            conn.execute(f"ALTER TABLE equipos ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    with conn:
        for fifa, (vid, val) in asignados.items():
            conn.execute("UPDATE equipos SET valor_plantilla=?, transfermarkt_id=? WHERE fifa_code=?", (val, vid, fifa))
    sin = [e.fifa_code for e in equipos if e.fifa_code not in asignados]
    conn.close()

    print(f"valor/transfermarkt_id asignado: {len(asignados)}/{len(equipos)}")
    if sin:
        print("sin datos (conciliar nombre):", ", ".join(sin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
