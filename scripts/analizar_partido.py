from __future__ import annotations

import sys

from src.config import load_config
from src.db.database import connect
from src.modelo.dixon_coles import Ajustes, ParametrosModelo, lambdas, matriz_marcadores, mercados
from src.modelo.valor import ev, sin_vig

HOSTS = {"USA", "MEX", "CAN"}


def tasa_base(conn) -> float:
    filas = conn.execute("SELECT goles_local, goles_visita FROM resultados").fetchall()
    if not filas:
        return 1.35
    goles = sum(r["goles_local"] + r["goles_visita"] for r in filas)
    return goles / (2 * len(filas))


def main(local: str, visita: str) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    eq = {r["fifa_code"]: r for r in conn.execute("SELECT fifa_code, nombre, elo FROM equipos")}
    if local not in eq or visita not in eq or eq[local]["elo"] is None or eq[visita]["elo"] is None:
        print("fifa_code sin datos (revisa codigo o ingesta de Elo)")
        return 1

    base = tasa_base(conn)
    par = ParametrosModelo(tasa_base=base, ventaja_local_elo=80.0 if local in HOSTS else 0.0)
    lh, la = lambdas(eq[local]["elo"], eq[visita]["elo"], par, Ajustes())
    prob = mercados(matriz_marcadores(lh, la, par))

    partido = conn.execute(
        "SELECT p.id FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id WHERE el.fifa_code=? AND ev.fifa_code=?",
        (local, visita),
    ).fetchone()
    cuotas: dict[str, float] = {}
    if partido:
        for r in conn.execute(
            "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'",
            (partido["id"],),
        ):
            cuotas[r["seleccion"]] = r["cuota"]
    conn.close()

    clave = {"1": local, "X": "X", "2": visita}
    novig = sin_vig({s: cuotas[clave[s]] for s in ("1", "X", "2")}) if len(cuotas) >= 3 else {}

    print(f"{eq[local]['nombre']} (Elo {int(eq[local]['elo'])}) vs {eq[visita]['nombre']} (Elo {int(eq[visita]['elo'])})")
    print(f"tasa base torneo {base:.2f} gol/equipo | lambda {lh:.2f} - {la:.2f} | goles esperados {lh + la:.2f}")
    print()
    print("mercado    modelo   pinnacle   cuota      EV")
    for sel, etq in (("1", local), ("X", "Empate"), ("2", visita)):
        pm = prob[sel] * 100
        pn = f"{novig[sel] * 100:5.1f}%" if sel in novig else "   -  "
        cu = cuotas.get(clave[sel])
        e = f"{ev(prob[sel], cu):+.3f}" if cu else "  -"
        print(f"  {etq:8} {pm:5.1f}%   {pn}     {cu if cu else '-':>5}   {e}")
    print()
    print(f"  Over 2.5  {prob['over25'] * 100:5.1f}%   |  Under 2.5  {prob['under25'] * 100:5.1f}%")
    print(f"  BTTS Si   {prob['btts_si'] * 100:5.1f}%   |  BTTS No    {prob['btts_no'] * 100:5.1f}%")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(main((args[0] if args else "ARG").upper(), (args[1] if len(args) > 1 else "AUT").upper()))
