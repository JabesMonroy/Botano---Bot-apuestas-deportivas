from __future__ import annotations

import math
import sqlite3

from scipy.optimize import minimize_scalar

from src.modelo.dixon_coles import Ajustes, ParametrosModelo, lambdas, matriz_marcadores, mercados
from src.modelo.parametros import HOSTS
from src.modelo.valor import sin_vig

Dato = tuple[float, float, bool, dict[str, float]]


def datos_calibracion(conn: sqlite3.Connection) -> list[Dato]:
    filas = conn.execute(
        "SELECT p.id, el.fifa_code fl, el.elo elo_l, ev.fifa_code fv, ev.elo elo_v "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id "
        "WHERE el.elo IS NOT NULL AND ev.elo IS NOT NULL"
    ).fetchall()
    datos: list[Dato] = []
    for f in filas:
        cuotas = {
            r["seleccion"]: r["cuota"]
            for r in conn.execute(
                "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'",
                (f["id"],),
            )
        }
        if not {f["fl"], "X", f["fv"]} <= cuotas.keys():
            continue
        nv = sin_vig({"1": cuotas[f["fl"]], "X": cuotas["X"], "2": cuotas[f["fv"]]})
        datos.append((f["elo_l"], f["elo_v"], f["fl"] in HOSTS, nv))
    return datos


def _probs_1x2(elo_l: float, elo_v: float, host: bool, tasa_base: float, beta: float, rho: float) -> dict[str, float]:
    par = ParametrosModelo(tasa_base=tasa_base, beta_elo=beta, rho=rho, ventaja_local_elo=80.0 if host else 0.0)
    lh, la = lambdas(elo_l, elo_v, par, Ajustes())
    m = mercados(matriz_marcadores(lh, la, par))
    return {k: m[k] for k in ("1", "X", "2")}


def cross_entropy(beta: float, datos: list[Dato], tasa_base: float, rho: float) -> float:
    eps = 1e-9
    total = 0.0
    for elo_l, elo_v, host, nv in datos:
        pm = _probs_1x2(elo_l, elo_v, host, tasa_base, beta, rho)
        total += -sum(nv[k] * math.log(max(pm[k], eps)) for k in ("1", "X", "2"))
    return total / len(datos)


def calibrar_beta(datos: list[Dato], tasa_base: float, rho: float, beta0: float = 0.20) -> tuple[float, float, float]:
    ce0 = cross_entropy(beta0, datos, tasa_base, rho)
    res = minimize_scalar(
        lambda b: cross_entropy(b, datos, tasa_base, rho),
        bounds=(0.05, 0.60),
        method="bounded",
    )
    return float(res.x), ce0, float(res.fun)
