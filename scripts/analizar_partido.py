from __future__ import annotations

import sys

from src.config import load_config
from src.db.database import connect
from src.modelo.valor import ev
from src.reporte import analizar_1x2


def main(local: str, visita: str) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    a = analizar_1x2(conn, cfg.data_dir, local, visita)
    conn.close()
    if a is None:
        print("no se pudo analizar (codigo o datos faltantes)")
        return 1

    clave = {"1": a.local, "X": "X", "2": a.visita}
    print(f"{a.nombre_local} vs {a.nombre_visita}  [{a.metodo}]")
    print(f"lambda {a.lh:.2f} - {a.la:.2f} | goles esperados {a.lh + a.la:.2f}")
    print()
    print("mercado    modelo   pinnacle   trabajo   cuota      EV")
    for sel, etq in (("1", a.local), ("X", "Empate"), ("2", a.visita)):
        pn = f"{a.novig[sel] * 100:5.1f}%" if sel in a.novig else "   -  "
        cu = a.cuotas.get(clave[sel])
        e = (f"{ev(a.trabajo[sel], cu):+.3f}" if a.fiable else "n/f") if cu else "  -"
        print(f"  {etq:8} {a.modelo[sel] * 100:5.1f}%   {pn}    {a.trabajo[sel] * 100:5.1f}%   {cu if cu else '-':>5}   {e}")
    print()
    print(f"  Over 2.5  {a.prob['over25'] * 100:5.1f}%   |  Under 2.5  {a.prob['under25'] * 100:5.1f}%")
    print(f"  BTTS Si   {a.prob['btts_si'] * 100:5.1f}%   |  BTTS No    {a.prob['btts_no'] * 100:5.1f}%")
    if a.corners_esp:
        print(f"  Corners esp. {a.corners_esp:.1f}   |  Tarjetas esp. {a.tarjetas_esp:.1f}" if a.tarjetas_esp else f"  Corners esp. {a.corners_esp:.1f}")
    if a.novig and not a.fiable:
        print(f"\n  AVISO: el modelo diverge {a.divergencia * 100:.0f}pp del mercado sharp -> EV no valido")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(main((args[0] if args else "ARG").upper(), (args[1] if len(args) > 1 else "AUT").upper()))
