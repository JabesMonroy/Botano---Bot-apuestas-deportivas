from __future__ import annotations

import sys
import unicodedata

from src.clients.football_data import FootballData
from src.config import load_config
from src.db.database import connect
from src.scrapers.transfermarkt import Transfermarkt


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def main(fifa: str) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    eq = conn.execute(
        "SELECT nombre, transfermarkt_id, football_data_id, valor_plantilla FROM equipos WHERE fifa_code=?", (fifa,)
    ).fetchone()
    if eq is None or eq["transfermarkt_id"] is None or eq["football_data_id"] is None:
        print("faltan transfermarkt_id/football_data_id (corre ingestar_valor)")
        conn.close()
        return 1

    kader = [(n, v) for n, _pos, v in Transfermarkt(cfg.cache_dir).kader(eq["transfermarkt_id"]) if v]
    fd = FootballData(cfg.football_data_key, cfg.cache_dir / "football_data").equipo(eq["football_data_id"])
    conn.close()

    convocados = [_norm(p.get("name", "")) for p in fd.get("squad", [])]
    ausentes = []
    for nombre, valor in kader:
        apellido = _norm(nombre).split()[-1] if nombre else ""
        if apellido and not any(apellido in c for c in convocados):
            ausentes.append((nombre, valor))

    total = eq["valor_plantilla"] or sum(v for _, v in kader)
    print(f"{eq['nombre']}: plantilla TM {len(kader)} jug. (€{total:.0f}m) | convocados football-data {len(fd.get('squad', []))}")
    ausentes.sort(key=lambda x: -x[1])
    if not ausentes:
        print("sin discrepancias: todos los jugadores valiosos de TM estan en la convocatoria.")
    else:
        impacto = sum(v for _, v in ausentes)
        print(f"posibles bajas/ausencias (en TM, no en convocatoria) — impacto €{impacto:.0f}m ({impacto / total * 100:.0f}% del valor):")
        for n, v in ausentes[:8]:
            print(f"  {n:26} €{v:5.0f}m")
        print("\n(cruce por apellido, aproximado; verificar con prensa antes de ajustar el modelo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main((sys.argv[1] if len(sys.argv) > 1 else "ARG").upper()))
