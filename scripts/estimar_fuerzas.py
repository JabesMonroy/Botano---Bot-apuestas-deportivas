from __future__ import annotations

import math

from src.config import load_config
from src.db.database import connect
from src.modelo.dixon_coles import Ajustes
from src.modelo.fuerzas import PESO_XG, _filas_mundial, ajustar, cargar_partidos, guardar, lambdas_desde_fuerzas

K_TORNEO = 40.0


def _mu_torneo(conn, params: dict) -> tuple[float, int]:
    obs = pred = 0.0
    n = 0
    for r in _filas_mundial(conn):
        ventaja = params["gamma"] if not r["neutral"] else 0.0
        res = lambdas_desde_fuerzas(r["h"], r["a"], params, Ajustes(), ventaja_local=ventaja)
        if res is None:
            continue
        goles = float(r["gh"]) + float(r["ga"])
        if r["xgh"] is not None and r["xgv"] is not None:
            objetivo = PESO_XG * (float(r["xgh"]) + float(r["xgv"])) + (1.0 - PESO_XG) * goles
        else:
            objetivo = goles
        obs += objetivo
        pred += res[0] + res[1]
        n += 1
    if n == 0 or pred <= 0.0 or obs <= 0.0:
        return 0.0, n
    return math.log(obs / pred) * n / (n + K_TORNEO), n


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    equipos, h, a, gh, ga, w, elo_norm, gflag, ref = cargar_partidos(conn, cfg.cache_dir)
    if len(equipos) < 2:
        print("histórico insuficiente (corre ingestar_historico)")
        return 1

    params = ajustar(equipos, h, a, gh, ga, w, elo_norm, gflag)
    mu_t, n_t = _mu_torneo(conn, params)
    params["mu_torneo"] = round(mu_t, 4)
    guardar(cfg.data_dir, params, ref)

    with conn:
        for api_id, v in params["fuerzas"].items():
            conn.execute(
                "UPDATE equipos SET fuerza_ataque=?, fuerza_defensa=? WHERE api_football_id=?",
                (v["ataque"], v["defensa"], int(api_id)),
            )

    print(f"equipos estimados: {len(equipos)} | partidos usados: {len(h)} | ref {ref.date()}")
    print(f"mu {params['mu']:.3f} | ventaja local x{math.exp(params['gamma']):.3f} | rho {params['rho']:.3f} | theta(Elo) {params['theta']:.3f}")
    print(f"mu_torneo {params['mu_torneo']:+.4f} (goles del Mundial vs modelo, {n_t} partidos, shrinkage k={K_TORNEO:.0f})")
    print("--- top ataque (de las 48) ---")
    for r in conn.execute(
        "SELECT fifa_code, fuerza_ataque, fuerza_defensa, elo FROM equipos "
        "WHERE fuerza_ataque IS NOT NULL ORDER BY fuerza_ataque DESC LIMIT 6"
    ):
        print(f"  {r['fifa_code']:4} atk {r['fuerza_ataque']:+.2f}  def {r['fuerza_defensa']:+.2f}  (Elo {int(r['elo'])})")
    cobertura = conn.execute("SELECT COUNT(*) FROM equipos WHERE fuerza_ataque IS NOT NULL").fetchone()[0]
    sin = [r["fifa_code"] for r in conn.execute("SELECT fifa_code FROM equipos WHERE fuerza_ataque IS NULL")]
    conn.close()
    print(f"48 con fuerzas estimadas: {cobertura}")
    if sin:
        print("sin fuerzas (fallback Elo):", ", ".join(sin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
