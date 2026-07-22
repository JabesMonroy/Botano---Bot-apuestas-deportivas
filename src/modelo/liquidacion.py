from __future__ import annotations

MERCADOS_AUTOMATICOS = {"1X2", "doble_oportunidad", "totals", "goles_local", "goles_visita", "btts"}


def _over_under(seleccion: str) -> tuple[str, float]:
    if seleccion.startswith("over"):
        return "over", float(seleccion[4:])
    return "under", float(seleccion[5:])


def resultado_mercado(mercado: str, seleccion: str, gl: int, gv: int) -> bool | None:
    if mercado == "1X2":
        real = "1" if gl > gv else ("X" if gl == gv else "2")
        return seleccion == real
    if mercado == "doble_oportunidad":
        return {"1X": gl >= gv, "X2": gl <= gv, "12": gl != gv}.get(seleccion)
    if mercado == "btts":
        ambos = gl > 0 and gv > 0
        return ambos if seleccion == "si" else not ambos
    if mercado == "totals":
        lado, linea = _over_under(seleccion)
        total = gl + gv
        return total > linea if lado == "over" else total < linea
    if mercado == "goles_local":
        lado, linea = _over_under(seleccion)
        return gl > linea if lado == "over" else gl < linea
    if mercado == "goles_visita":
        lado, linea = _over_under(seleccion)
        return gv > linea if lado == "over" else gv < linea
    return None
