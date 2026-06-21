from __future__ import annotations

import sys

from src.config import load_config
from src.db.database import connect
from src.modelo.bet_builder import PREDICADOS, prob_conjunta, prob_marginal
from src.modelo.valor import ev
from src.reporte import analizar_1x2


def _uso() -> int:
    print("uso: python -m scripts.bet_builder LOCAL-VISITA:mercado [...] [@cuota_combinada]")
    print("mercados:", ", ".join(PREDICADOS))
    return 1


def main(argv: list[str]) -> int:
    cuota = None
    selecciones = []
    for tok in argv:
        if tok.startswith("@"):
            cuota = float(tok[1:])
        elif ":" in tok and "-" in tok:
            partido, mercado = tok.split(":")
            local, visita = partido.upper().split("-")
            if mercado not in PREDICADOS:
                print(f"mercado no soportado: {mercado}")
                return _uso()
            selecciones.append((local, visita, mercado))
    if not selecciones:
        return _uso()

    grupos: dict[tuple[str, str], list[str]] = {}
    for local, visita, mercado in selecciones:
        grupos.setdefault((local, visita), []).append(mercado)

    cfg = load_config()
    conn = connect(cfg.db_path)
    p_correcta, p_naive, todo_fiable = 1.0, 1.0, True
    print(f"Bet builder: {len(selecciones)} selecciones en {len(grupos)} partido(s)\n")
    for (local, visita), mercados in grupos.items():
        a = analizar_1x2(conn, cfg.data_dir, local, visita)
        if a is None:
            print(f"{local}-{visita}: sin datos")
            conn.close()
            return 1
        marginales = {m: prob_marginal(a.matriz, m) for m in mercados}
        conjunta = prob_conjunta(a.matriz, mercados)
        naive = 1.0
        for m in mercados:
            naive *= marginales[m]
        p_correcta *= conjunta
        p_naive *= naive
        todo_fiable = todo_fiable and a.fiable
        detalle = "  ".join(f"{m}={marginales[m] * 100:.1f}%" for m in mercados)
        flag = "" if a.fiable else "  [poco fiable vs mercado]"
        print(f"{a.nombre_local} vs {a.nombre_visita}: {', '.join(mercados)}{flag}")
        print(f"  marginales: {detalle}")
        if len(mercados) > 1:
            print(f"  naive(multiplicado): {naive * 100:.1f}%  ->  correcto(correlacion): {conjunta * 100:.1f}%  ({(conjunta - naive) * 100:+.1f}pp)")
    conn.close()

    print("\nProbabilidad combinada:")
    print(f"  naive (multiplicacion):  {p_naive * 100:.1f}%")
    print(f"  correcta (correlacion):  {p_correcta * 100:.1f}%  ({(p_correcta - p_naive) * 100:+.1f}pp)")
    if cuota:
        impl = 1.0 / cuota
        print(f"\nCuota combinada {cuota} -> prob implicita {impl * 100:.1f}%")
        if todo_fiable:
            print(f"  EV (prob correcta): {ev(p_correcta, cuota):+.3f}")
        else:
            print("  EV: n/f (algun partido diverge del mercado sharp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
