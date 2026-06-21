from __future__ import annotations

import sys

from src.apuestas import registrar
from src.config import load_config
from src.db.database import connect


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("uso: python -m scripts.registrar_apuesta LOCAL VISITA SELECCION CUOTA [STAKE]")
        print("  SELECCION: 1 (local) | X (empate) | 2 (visita)")
        return 1
    local, visita, seleccion, cuota = argv[0].upper(), argv[1].upper(), argv[2].upper(), float(argv[3])
    stake = float(argv[4]) if len(argv) > 4 else None

    cfg = load_config()
    conn = connect(cfg.db_path)
    r = registrar(conn, cfg.data_dir, local, visita, seleccion, cuota, stake)
    conn.close()
    if r is None:
        print("no se pudo registrar (codigo, seleccion o partido invalido)")
        return 1

    print(f"Apuesta registrada: {local}-{visita} {r['seleccion']} @ {cuota}")
    print(f"  prob modelo (trabajo): {r['prob'] * 100:.1f}% | EV: {r['ev']:+.3f} | Kelly fracc.: {r['kelly_pct']:.2f}% del bankroll | stake: {r['stake']}")
    if r["ev"] <= 0:
        print("  AVISO: EV <= 0 segun el modelo (no recomendada). Registrada igualmente para seguimiento de CLV.")
    if not r["fiable"]:
        print("  AVISO: el modelo diverge del mercado sharp en este partido (poco fiable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
