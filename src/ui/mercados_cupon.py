from __future__ import annotations

from src.config import Config
from src.modelo.secundarios import over_under, over_under_nb
from src.ui.datos import params_tiros
from src.ui.formato import dist_goles, over_equipo, p_over_linea, primer_gol

MERCADOS_OVER_UNDER = {
    "goles_totales", "goles_local", "goles_visita", "corners_totales",
    "tarjetas_totales", "tiros_totales", "tiros_arco_totales", "saques_totales",
}

LINEA_SUGERIDA = {
    "goles_totales": 2.5, "goles_local": 1.5, "goles_visita": 1.5,
    "corners_totales": 9.5, "tarjetas_totales": 3.5,
    "tiros_totales": 24.5, "tiros_arco_totales": 8.5, "saques_totales": 15.5,
}

_NOMBRE_OU = {
    "goles_totales": "goles", "corners_totales": "córners", "tarjetas_totales": "tarjetas",
    "tiros_totales": "tiros", "tiros_arco_totales": "tiros al arco", "saques_totales": "saques de meta",
}


def mercados_disponibles(a) -> list[tuple[str, str]]:
    opciones = [
        ("1x2", "Ganador del partido (1X2)"),
        ("doble_oportunidad", "Doble oportunidad"),
        ("goles_totales", "Goles totales"),
        ("goles_local", f"Goles de {a.nombre_local}"),
        ("goles_visita", f"Goles de {a.nombre_visita}"),
        ("btts", "Ambos anotan"),
        ("primer_gol", "Primer gol del partido"),
    ]
    if a.corners_esp:
        opciones.append(("corners_totales", "Córners totales"))
    if a.tarjetas_esp:
        opciones.append(("tarjetas_totales", "Tarjetas totales"))
    opciones.append(("tiros_totales", "Tiros totales"))
    opciones.append(("tiros_arco_totales", "Tiros al arco totales"))
    if a.saques_local and a.saques_visita:
        opciones.append(("saques_totales", "Saques de meta totales"))
    return opciones


def lados_fijos(mercado: str, a) -> list[tuple[str, str]]:
    if mercado == "1x2":
        return [("1", f"Gana {a.nombre_local}"), ("X", "Empate"), ("2", f"Gana {a.nombre_visita}")]
    if mercado == "doble_oportunidad":
        return [("1X", f"{a.nombre_local} o empate"), ("X2", f"Empate o {a.nombre_visita}"), ("12", f"{a.nombre_local} o {a.nombre_visita}")]
    if mercado == "btts":
        return [("si", "Sí"), ("no", "No")]
    if mercado == "primer_gol":
        return [("local", f"Marca primero {a.nombre_local}"), ("visita", f"Marca primero {a.nombre_visita}"), ("ninguno", "Sin goles (0-0)")]
    return []


def etiqueta_over_under(mercado: str, a, linea: float, lado: str) -> str:
    if mercado == "goles_local":
        sujeto = f"goles de {a.nombre_local}"
    elif mercado == "goles_visita":
        sujeto = f"goles de {a.nombre_visita}"
    else:
        sujeto = _NOMBRE_OU[mercado]
    verbo = "Más de" if lado == "over" else "Menos de"
    return f"{verbo} {linea} {sujeto}"


def calcular_prob(cfg: Config, a, tarjetas_final: float | None, mercado: str, lado: str, linea: float | None) -> float | None:
    if mercado == "1x2":
        return a.trabajo[lado]
    if mercado == "doble_oportunidad":
        return {"1X": a.trabajo["1"] + a.trabajo["X"], "X2": a.trabajo["X"] + a.trabajo["2"], "12": a.trabajo["1"] + a.trabajo["2"]}[lado]
    if mercado == "btts":
        if a.btts_mercado:
            return a.btts_mercado["trabajo"][lado]
        return a.prob["btts_si"] if lado == "si" else 1 - a.prob["btts_si"]
    if mercado == "primer_gol":
        p_local, p_visita, p_ninguno = primer_gol(a.lh, a.la, float(a.matriz[0, 0]))
        return {"local": p_local, "visita": p_visita, "ninguno": p_ninguno}[lado]

    if mercado == "goles_totales":
        p_over = p_over_linea(dist_goles(a.matriz), linea)
    elif mercado == "goles_local":
        p_over = over_equipo(a.matriz, 0, linea)
    elif mercado == "goles_visita":
        p_over = over_equipo(a.matriz, 1, linea)
    elif mercado == "corners_totales":
        if not a.corners_esp:
            return None
        p_over = over_under(a.corners_esp, [linea])[linea]
    elif mercado == "tarjetas_totales":
        if not tarjetas_final:
            return None
        p_over = over_under_nb(tarjetas_final, a.tarjetas_ratio_var, [linea])[linea]
    elif mercado in ("tiros_totales", "tiros_arco_totales"):
        k, ratio_arco = params_tiros(cfg)
        base = (a.lh + a.la) / k
        if mercado == "tiros_arco_totales":
            base *= ratio_arco
        p_over = over_under(base, [linea])[linea]
    elif mercado == "saques_totales":
        if not (a.saques_local and a.saques_visita):
            return None
        p_over = over_under(a.saques_local + a.saques_visita, [linea])[linea]
    else:
        return None
    return p_over if lado == "over" else 1 - p_over
