from __future__ import annotations

import sys
import unicodedata
from collections import defaultdict

from src.clients.odds_api import OddsApi
from src.config import load_config
from src.db.database import connect
from src.modelo.torneo import cargar_estado, simular

SPORT = "soccer_fifa_world_cup_winner"


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def mercado_campeon(cfg, fifa_por_odds) -> dict[str, float]:
    client = OddsApi(cfg.odds_api_key, cfg.cache_dir / "odds_api")
    try:
        eventos = client.odds(SPORT, regions="us,uk,eu", markets="outrights", bookmakers="")
    finally:
        client.close()
    acc: dict[str, list] = defaultdict(list)
    for ev in eventos:
        for book in ev.get("bookmakers", []):
            for mk in book.get("markets", []):
                for o in mk.get("outcomes", []):
                    fifa = fifa_por_odds.get(_norm(o.get("name", "")))
                    if fifa and o.get("price"):
                        acc[fifa].append(1.0 / o["price"])
    if not acc:
        return {}
    implied = {k: sum(v) / len(v) for k, v in acc.items()}
    s = sum(implied.values())
    return {k: v / s for k, v in implied.items()}


def main(n_iter: int) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    estado = cargar_estado(conn, cfg.data_dir)
    eq = estado[0]
    fifa = {api: r["fifa_code"] for api, r in eq.items()}
    fifa_por_odds = {
        _norm(r["odds_api_name"]): r["fifa_code"]
        for r in conn.execute("SELECT odds_api_name, fifa_code FROM equipos WHERE odds_api_name != ''")
    }
    conn.close()

    res = simular(estado, n_iter)
    avanza = {fifa[a]: c / n_iter for a, c in res["avanza"].items()}
    campeon = {fifa[a]: c / n_iter for a, c in res["campeon"].items()}
    finalista = {fifa[a]: c / n_iter for a, c in res["finalista"].items()}
    mercado = mercado_campeon(cfg, fifa_por_odds)

    print(f"Simulacion Monte Carlo del Mundial 2026 ({n_iter} iteraciones)")
    print("(cuadro de eliminatorias = sorteo aleatorio entre los 32, aproximacion documentada)\n")
    print("equipo  P(avanza)  P(final)  P(campeon)  mercado   dif")
    for f in sorted(campeon, key=campeon.get, reverse=True)[:16]:
        m = mercado.get(f)
        mtxt = f"{m * 100:5.1f}%" if m else "  -  "
        dif = f"{(campeon[f] - m) * 100:+5.1f}" if m else "  - "
        print(f"  {f:4}  {avanza.get(f, 0) * 100:6.1f}%  {finalista.get(f, 0) * 100:6.1f}%  {campeon[f] * 100:6.1f}%   {mtxt}   {dif}")
    print("\nAviso: P(avanza) es robusta; P(campeon) del modelo amplifica sus sesgos (no capta calidad de plantilla).")
    print("Grandes divergencias con el mercado (ej. COL/ARG sobre, FRA bajo) son fallos del modelo, no valor.")
    return 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    raise SystemExit(main(n))
