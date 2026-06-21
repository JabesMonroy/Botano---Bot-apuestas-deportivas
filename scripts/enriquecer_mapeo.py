from __future__ import annotations

import sys
import unicodedata

from src.clients.football_data import FootballData
from src.config import load_config
from src.mapeo import cargar_csv, guardar_csv


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower()


def main() -> int:
    cfg = load_config()
    if not cfg.football_data_key:
        print("Falta FOOTBALL_DATA_KEY en .env")
        return 1

    csv_path = cfg.data_dir / "referencia" / "equipos_mundial2026.csv"
    equipos = cargar_csv(csv_path)
    por_fifa = {e.fifa_code: e for e in equipos}
    por_nombre: dict[str, object] = {}
    for e in equipos:
        por_nombre[_norm(e.nombre)] = e
        if e.odds_api_name:
            por_nombre[_norm(e.odds_api_name)] = e

    client = FootballData(cfg.football_data_key, cfg.cache_dir / "football_data")
    try:
        st = client.standings()
    finally:
        client.close()

    vistos: dict[int, dict] = {}
    for grupo in st.get("standings", []):
        if grupo.get("type") not in (None, "TOTAL"):
            continue
        for fila in grupo.get("table", []):
            t = fila.get("team", {})
            if t.get("id") is not None:
                vistos[t["id"]] = t

    emparejados = 0
    sin_match = []
    for t in vistos.values():
        tla = (t.get("tla") or "").upper()
        nombre_fd = t.get("name", "")
        equipo = (
            por_fifa.get(tla)
            or por_nombre.get(_norm(nombre_fd))
            or por_nombre.get(_norm(t.get("shortName", "")))
        )
        if equipo is None:
            sin_match.append(f"{tla} {nombre_fd} (id {t.get('id')})")
            continue
        equipo.football_data_id = t.get("id")
        equipo.football_data_name = nombre_fd
        emparejados += 1

    guardar_csv(csv_path, equipos)
    sin_id = sum(1 for e in equipos if not e.football_data_id)
    print(f"equipos football-data: {len(vistos)} | emparejados: {emparejados} | en CSV sin id: {sin_id}")
    if sin_match:
        print("FD sin match en CSV (conciliar):")
        for s in sin_match:
            print("  -", s)
    return 1 if sin_match or sin_id else 0


if __name__ == "__main__":
    sys.exit(main())
