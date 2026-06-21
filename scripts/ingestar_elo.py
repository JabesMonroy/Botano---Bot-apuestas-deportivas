from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

from src.config import load_config
from src.db.database import connect
from src.mapeo import cargar_csv, guardar_csv
from src.scrapers.eloratings import EloRatings


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def main() -> int:
    cfg = load_config()
    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    equipos = cargar_csv(csv_path)

    idx: dict[str, object] = {}
    for e in equipos:
        for n in (e.nombre, e.odds_api_name, e.football_data_name):
            if n:
                idx.setdefault(_norm(n), e)

    ratings = EloRatings(cfg.cache_dir / "eloratings").ratings()
    elo_por_fifa: dict[str, int] = {}
    for code, nombre, elo, alias in ratings:
        eq = idx.get(_norm(nombre))
        if eq is None:
            eq = next((idx[_norm(a)] for a in alias if _norm(a) in idx), None)
        if eq is None:
            continue
        eq.eloratings_name = nombre
        elo_por_fifa[eq.fifa_code] = elo

    guardar_csv(csv_path, equipos)

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = connect(cfg.db_path)
    try:
        with conn:
            for e in equipos:
                if e.fifa_code in elo_por_fifa:
                    conn.execute(
                        "UPDATE equipos SET elo=?, eloratings_name=?, actualizado=? WHERE fifa_code=?",
                        (elo_por_fifa[e.fifa_code], e.eloratings_name, ahora, e.fifa_code),
                    )
        sin_elo = [e.fifa_code for e in equipos if e.fifa_code not in elo_por_fifa]
    finally:
        conn.close()

    print(f"selecciones con Elo: {len(elo_por_fifa)} / {len(equipos)}")
    if sin_elo:
        print("sin Elo (conciliar nombre):", ", ".join(sin_elo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
