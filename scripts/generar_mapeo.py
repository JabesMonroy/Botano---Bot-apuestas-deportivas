from __future__ import annotations

import sys
import unicodedata

from src.clients.api_football import ApiFootball
from src.config import load_config
from src.mapeo import EquipoMapeo, cargar_csv, guardar_csv

WORLD_CUP_LEAGUE = 1
SEASON = 2026


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower()


def main() -> int:
    cfg = load_config()
    if not cfg.api_football_key:
        print("Falta API_FOOTBALL_KEY en .env")
        return 1

    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    existentes = cargar_csv(csv_path) if csv_path.exists() else []
    por_code = {e.fifa_code: e for e in existentes}
    por_nombre = {_norm(e.nombre): e for e in existentes}

    client = ApiFootball(cfg.api_football_key, cfg.api_football_host, cfg.cache_dir / "api_football")
    try:
        data = client.teams(league=WORLD_CUP_LEAGUE, season=SEASON)
    finally:
        client.close()

    respuesta = data.get("response", [])
    nuevos = 0
    for item in respuesta:
        team = item.get("team", {})
        api_id = team.get("id")
        nombre = team.get("name", "")
        code = (team.get("code") or "").upper()
        equipo = por_code.get(code) or por_nombre.get(_norm(nombre))
        if equipo is None:
            equipo = EquipoMapeo(fifa_code=code, nombre=nombre)
            existentes.append(equipo)
            if code:
                por_code[code] = equipo
            por_nombre[_norm(nombre)] = equipo
            nuevos += 1
        equipo.api_football_id = api_id
        if not equipo.fifa_code and code:
            equipo.fifa_code = code

    guardar_csv(csv_path, existentes)
    print(f"{len(respuesta)} equipos del Mundial (liga {WORLD_CUP_LEAGUE}, {SEASON}); {nuevos} nuevos. CSV actualizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
