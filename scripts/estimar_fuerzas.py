from __future__ import annotations

import math

from src.config import load_config
from src.db.database import connect
from src.modelo.fuerzas import ajustar, cargar_partidos, guardar


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    equipos, h, a, gh, ga, w, ref = cargar_partidos(conn)
    if len(equipos) < 2:
        print("histórico insuficiente (corre ingestar_historico)")
        return 1

    params = ajustar(equipos, h, a, gh, ga, w)
    guardar(cfg.data_dir, params, ref)

    with conn:
        for api_id, v in params["fuerzas"].items():
            conn.execute(
                "UPDATE equipos SET fuerza_ataque=?, fuerza_defensa=? WHERE api_football_id=?",
                (v["ataque"], v["defensa"], int(api_id)),
            )

    print(f"equipos estimados: {len(equipos)} | partidos usados: {len(h)} | ref {ref.date()}")
    print(f"mu {params['mu']:.3f} | ventaja local x{math.exp(params['gamma']):.3f} | rho {params['rho']:.3f}")
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
