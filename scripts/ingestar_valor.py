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
    valores = Transfermarkt(cfg.cache_dir).valores()
    idx = {_norm(n): v for n, v in valores.items()}

    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    equipos = cargar_csv(csv_path)
    asignados: dict[str, float] = {}
    for e in equipos:
        candidatos = (e.odds_api_name, e.eloratings_name, e.football_data_name, e.nombre, *OVERRIDES.get(e.fifa_code, ()))
        for n in candidatos:
            if n and _norm(n) in idx:
                asignados[e.fifa_code] = idx[_norm(n)]
                break

    conn = connect(cfg.db_path)
    try:
        conn.execute("ALTER TABLE equipos ADD COLUMN valor_plantilla REAL")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    with conn:
        for fifa, v in asignados.items():
            conn.execute("UPDATE equipos SET valor_plantilla=? WHERE fifa_code=?", (v, fifa))
    sin = [e.fifa_code for e in equipos if e.fifa_code not in asignados]
    conn.close()

    print(f"valor de plantilla asignado: {len(asignados)}/{len(equipos)} (fuente Transfermarkt, en M€)")
    if sin:
        print("sin valor (conciliar nombre):", ", ".join(sin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
