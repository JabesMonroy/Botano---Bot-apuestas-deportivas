from __future__ import annotations

import sys
import unicodedata

from src.clients.odds_api import OddsApi
from src.config import load_config
from src.mapeo import cargar_csv

SPORT = "soccer_fifa_world_cup"


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower()


def main() -> int:
    cfg = load_config()
    if not cfg.odds_api_key:
        print("Falta ODDS_API_KEY en .env")
        return 1

    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    equipos = cargar_csv(csv_path)
    en_csv = {_norm(e.odds_api_name) for e in equipos if e.odds_api_name}

    client = OddsApi(cfg.odds_api_key, cfg.cache_dir / "odds_api")
    try:
        eventos = client.odds(SPORT, markets="h2h", ttl=600)
    finally:
        client.close()

    en_api: set[str] = set()
    for ev in eventos:
        en_api.add(ev["home_team"])
        en_api.add(ev["away_team"])

    faltan = sorted(n for n in en_api if _norm(n) not in en_csv)

    print(f"equipos en CSV: {len(equipos)} | equipos en Odds API (partido proximo): {len(en_api)}")
    if faltan:
        print("EN API PERO NO EN CSV (conciliar odds_api_name):")
        for n in faltan:
            print("  -", n)
        return 1
    print("OK: todos los equipos de la API estan mapeados en el CSV.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
