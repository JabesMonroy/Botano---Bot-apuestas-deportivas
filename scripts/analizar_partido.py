from __future__ import annotations

import sys

from src.config import load_config
from src.db.database import connect
from src.modelo.dixon_coles import Ajustes, ParametrosModelo, lambdas, matriz_marcadores, mercados
from src.modelo.fuerzas import cargar as cargar_fuerzas
from src.modelo.fuerzas import lambdas_desde_fuerzas
from src.modelo.parametros import HOSTS, cargar
from src.modelo.valor import ev, sin_vig


def main(local: str, visita: str) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    eq = {
        r["fifa_code"]: r
        for r in conn.execute("SELECT fifa_code, nombre, elo, api_football_id FROM equipos")
    }
    if local not in eq or visita not in eq:
        print("fifa_code no encontrado")
        return 1

    aj = Ajustes()
    fuerzas = cargar_fuerzas(cfg.data_dir)
    res = None
    if fuerzas and eq[local]["api_football_id"] and eq[visita]["api_football_id"]:
        ventaja = fuerzas["gamma"] if local in HOSTS else 0.0
        res = lambdas_desde_fuerzas(
            eq[local]["api_football_id"], eq[visita]["api_football_id"], fuerzas, aj, ventaja_local=ventaja
        )
    if res is not None:
        metodo = "fuerzas (Dixon-Coles historico)"
        lh, la = res
        par = ParametrosModelo(tasa_base=0.0, rho=fuerzas["rho"])
    else:
        if eq[local]["elo"] is None or eq[visita]["elo"] is None:
            print("sin fuerzas ni Elo para el par")
            return 1
        metodo = "Elo (fallback)"
        par = cargar(cfg.data_dir, conn, local_es_host=local in HOSTS)
        lh, la = lambdas(eq[local]["elo"], eq[visita]["elo"], par, aj)

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

    print(f"{eq[local]['nombre']} vs {eq[visita]['nombre']}  [{metodo}]")
    print(f"lambda {lh:.2f} - {la:.2f} | goles esperados {lh + la:.2f}")
    print()
    print("mercado    modelo   pinnacle   cuota      EV")
    for sel, etq in (("1", local), ("X", "Empate"), ("2", visita)):
        pn = f"{novig[sel] * 100:5.1f}%" if sel in novig else "   -  "
        cu = cuotas.get(clave[sel])
        e = f"{ev(prob[sel], cu):+.3f}" if cu else "  -"
        print(f"  {etq:8} {prob[sel] * 100:5.1f}%   {pn}     {cu if cu else '-':>5}   {e}")
    print()
    print(f"  Over 2.5  {prob['over25'] * 100:5.1f}%   |  Under 2.5  {prob['under25'] * 100:5.1f}%")
    print(f"  BTTS Si   {prob['btts_si'] * 100:5.1f}%   |  BTTS No    {prob['btts_no'] * 100:5.1f}%")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(main((args[0] if args else "ARG").upper(), (args[1] if len(args) > 1 else "AUT").upper()))
