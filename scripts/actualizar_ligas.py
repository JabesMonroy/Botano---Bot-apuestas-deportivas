from __future__ import annotations

from src.clients.football_data import FootballData
from src.clients.odds_api import OddsApi
from src.config import Config, load_config
from src.db.database import connect
from src.ingesta import ingestar_cuotas, ingestar_partidos, ingestar_resultados, ingestar_standings
from src.ligas import LIGAS, Liga


def actualizar_liga(cfg: Config, liga: Liga, liga_id: int) -> dict:
    conn = connect(cfg.db_path)
    fd = FootballData(cfg.football_data_key, cfg.cache_dir / "football_data")
    try:
        np_ = ingestar_partidos(conn, fd, liga.fd_org, liga_id)
        nr = ingestar_resultados(conn, fd, liga.fd_org)
        ns = ingestar_standings(conn, fd, liga.fd_org, grupo_default=liga.codigo)
    finally:
        fd.close()

    nc = {"1x2": 0, "totals": 0, "btts": 0}
    if liga.odds_api:
        odds = OddsApi(cfg.odds_api_key, cfg.cache_dir / "odds_api")
        try:
            nc = ingestar_cuotas(conn, odds, sport=liga.odds_api)
        finally:
            odds.close()
    conn.close()
    return {"partidos": np_, "resultados": nr, "standings": ns, "cuotas": nc}


def actualizar_todas(cfg: Config) -> dict[str, dict]:
    conn = connect(cfg.db_path)
    liga_id = {r["codigo"]: r["id"] for r in conn.execute("SELECT id, codigo FROM ligas")}
    conn.close()

    resultado: dict[str, dict] = {}
    for liga in LIGAS:
        if liga.codigo not in liga_id or not liga.fd_org:
            continue
        resultado[liga.codigo] = actualizar_liga(cfg, liga, liga_id[liga.codigo])

    if "CO1" in liga_id:
        from scripts.actualizar_betplay import actualizar as actualizar_betplay
        resultado["CO1"] = actualizar_betplay(cfg)
    return resultado


def main() -> int:
    cfg = load_config()
    for codigo, r in actualizar_todas(cfg).items():
        liga = next(l for l in LIGAS if l.codigo == codigo)
        if codigo == "CO1":
            print(f"{liga.nombre}: partidos {r['partidos']} | resultados {r['resultados']} | equipos nuevos {r['equipos_nuevos']}")
        else:
            print(
                f"{liga.nombre}: partidos {r['partidos']} | resultados {r['resultados']} | standings {r['standings']} | "
                f"cuotas 1X2 {r['cuotas']['1x2']} · totals {r['cuotas']['totals']} · btts {r['cuotas']['btts']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
