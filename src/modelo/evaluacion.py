from __future__ import annotations

from src.modelo.dixon_coles import Ajustes, ParametrosModelo, matriz_marcadores, mercados
from src.modelo.fuerzas import lambdas_desde_fuerzas


def rps(p, outcome: int) -> float:
    c1 = p[0]
    c2 = p[0] + p[1]
    e1 = 1.0 if outcome == 0 else 0.0
    e12 = 1.0 if outcome in (0, 1) else 0.0
    return 0.5 * ((c1 - e1) ** 2 + (c2 - e12) ** 2)


def resultado(gh: int, ga: int) -> int:
    return 0 if gh > ga else (1 if gh == ga else 2)


def prob_fuerzas(api_h: int, api_a: int, params: dict, ventaja: float = 0.0):
    res = lambdas_desde_fuerzas(api_h, api_a, params, Ajustes(), ventaja_local=ventaja)
    if res is None:
        return None
    lh, la = res
    m = mercados(matriz_marcadores(lh, la, ParametrosModelo(tasa_base=0.0, rho=params["rho"])))
    return (m["1"], m["X"], m["2"])


def media(xs) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def estrato(p) -> str:
    fav = max(p[0], p[2])
    if fav >= 0.60:
        return "facil"
    if fav < 0.45:
        return "renido"
    return "medio"
