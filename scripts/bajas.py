from __future__ import annotations

import sys

from src.config import load_config
from src.db.database import connect
from src.plantillas import detectar_ausencias


def main(fifa: str) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    eq = conn.execute(
        "SELECT nombre, transfermarkt_id, football_data_id, valor_plantilla FROM equipos WHERE fifa_code=?", (fifa,)
    ).fetchone()
    conn.close()
    if eq is None or not eq["transfermarkt_id"] or not eq["football_data_id"]:
        print("faltan datos del equipo (corre ingestar_valor)")
        return 1

    ausentes = detectar_ausencias(cfg, eq["transfermarkt_id"], eq["football_data_id"])
    total = eq["valor_plantilla"] or 1
    print(f"{eq['nombre']}: ausencias detectadas (plantilla habitual vs convocatoria oficial)")
    if not ausentes:
        print("  ninguna — todos los jugadores valiosos están en la convocatoria.")
    else:
        impacto = sum(v for _, v in ausentes)
        for n, v in ausentes[:10]:
            print(f"  {n:26} €{v:5.0f}m")
        print(f"  impacto total: €{impacto:.0f}m ({impacto / total * 100:.0f}% del valor de plantilla)")
    print("\n(cruce por apellido, aproximado; verifica con prensa antes de apostar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main((sys.argv[1] if len(sys.argv) > 1 else "ARG").upper()))
