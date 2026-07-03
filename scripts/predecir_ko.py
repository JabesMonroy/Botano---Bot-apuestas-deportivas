from __future__ import annotations

import sys

import numpy as np

from src.config import load_config
from src.db.database import connect
from src.modelo.dixon_coles import ParametrosModelo, matriz_marcadores
from src.reporte import Analisis, analizar_1x2

FASES = ["LAST_32", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "THIRD_PLACE", "FINAL"]
TITULO = {
    "LAST_32": "16avos de final",
    "LAST_16": "Octavos de final",
    "QUARTER_FINALS": "Cuartos de final",
    "SEMI_FINALS": "Semifinales",
    "THIRD_PLACE": "Tercer puesto",
    "FINAL": "Final",
}


def clasifica(a: Analisis) -> tuple[float, float]:
    prorroga = matriz_marcadores(a.lh / 3.0, a.la / 3.0, ParametrosModelo(tasa_base=0.0, rho=a.rho))
    p1e = float(np.tril(prorroga, -1).sum())
    pxe = float(np.trace(prorroga))
    av1 = a.modelo["1"] + a.modelo["X"] * (p1e + 0.5 * pxe)
    return av1, 1.0 - av1


def cruces(conn, fase: str):
    return conn.execute(
        "SELECT el.fifa_code fh, ev.fifa_code fv, p.fecha "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id "
        "WHERE p.fase=? ORDER BY p.fecha",
        (fase,),
    ).fetchall()


def main(fase: str | None) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    objetivo = [fase] if fase else FASES
    hubo = False

    for f in objetivo:
        filas = cruces(conn, f)
        if not filas:
            continue
        hubo = True
        print(f"\n=== {TITULO.get(f, f)} ===")
        print("(1/X/2 = resultado a 90'. CLASIFICA incluye prorroga y penales -> mercado 'Para avanzar'.")
        print(" Cuota justa = cuota minima sin margen; hay valor si Betano paga MAS que eso al avance.)\n")
        print(f"{'Cruce':<34}{'1':>5}{'X':>5}{'2':>5}  {'->prorr':>8}   {'CLASIFICA':<16}{'P':>5}{'justa':>7}")
        print("-" * 92)
        for r in filas:
            a = analizar_1x2(conn, cfg.data_dir, r["fh"], r["fv"])
            if a is None:
                print(f"{r['fh']} vs {r['fv']:<28} sin datos")
                continue
            p1, px, p2 = a.modelo["1"], a.modelo["X"], a.modelo["2"]
            av1, av2 = clasifica(a)
            gana = a.nombre_local if av1 >= av2 else a.nombre_visita
            pg = max(av1, av2)
            cruce = f"{a.nombre_local} vs {a.nombre_visita}"
            print(
                f"{cruce[:33]:<34}{p1*100:4.0f}%{px*100:4.0f}%{p2*100:4.0f}%  {px*100:6.0f}%   "
                f"{gana[:14]:<14} {pg*100:3.0f}% {1/pg:6.2f}"
            )

    conn.close()
    if not hubo:
        print("no hay cruces de eliminacion directa cargados todavia")
        return 1
    return 0


if __name__ == "__main__":
    arg = sys.argv[1].upper() if len(sys.argv) > 1 else None
    raise SystemExit(main(arg))
