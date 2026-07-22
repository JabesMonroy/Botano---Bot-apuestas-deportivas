from __future__ import annotations

import pandas as pd

from src.config import Config
from src.db.database import connect
from src.modelo.bet_builder import prob_conjunta, prob_marginal
from src.modelo.secundarios import over_under, over_under_nb
from src.reporte import analizar_club
from src.ui.formato import pct, primer_gol

MERCADOS_COMBI = {
    "Gana local": ("g", "1"),
    "Empate": ("g", "X"),
    "Gana visita": ("g", "2"),
    "Local o empate (1X)": ("g", "1X"),
    "Empate o visita (X2)": ("g", "X2"),
    "Local o visita, no empate (12)": ("g", "12"),
    "Ambos anotan": ("g", "btts"),
    "No ambos anotan": ("g", "nobtts"),
    "Más de 0.5 goles": ("g", "over0.5"),
    "Más de 1.5 goles": ("g", "over1.5"),
    "Menos de 1.5 goles": ("g", "under1.5"),
    "Más de 2.5 goles": ("g", "over2.5"),
    "Menos de 2.5 goles": ("g", "under2.5"),
    "Más de 3.5 goles": ("g", "over3.5"),
    "Menos de 3.5 goles": ("g", "under3.5"),
    "Más de 4.5 goles": ("g", "over4.5"),
    "Menos de 4.5 goles": ("g", "under4.5"),
    "Local marca +0.5": ("g", "loc0.5"),
    "Local marca +1.5": ("g", "loc1.5"),
    "Visita marca +0.5": ("g", "vis0.5"),
    "Visita marca +1.5": ("g", "vis1.5"),
    "Primer gol: local": ("pg", "l"),
    "Primer gol: visita": ("pg", "v"),
    "Primer gol: ninguno (0-0)": ("pg", "n"),
    "Más de 5.5 córners": ("c", 5.5, "o"),
    "Menos de 5.5 córners": ("c", 5.5, "u"),
    "Más de 6.5 córners": ("c", 6.5, "o"),
    "Más de 7.5 córners": ("c", 7.5, "o"),
    "Menos de 7.5 córners": ("c", 7.5, "u"),
    "Más de 8.5 córners": ("c", 8.5, "o"),
    "Menos de 8.5 córners": ("c", 8.5, "u"),
    "Más de 9.5 córners": ("c", 9.5, "o"),
    "Menos de 9.5 córners": ("c", 9.5, "u"),
    "Más de 10.5 córners": ("c", 10.5, "o"),
    "Menos de 10.5 córners": ("c", 10.5, "u"),
    "Más de 11.5 córners": ("c", 11.5, "o"),
    "Más de 1.5 tarjetas": ("t", 1.5, "o"),
    "Más de 2.5 tarjetas": ("t", 2.5, "o"),
    "Menos de 2.5 tarjetas": ("t", 2.5, "u"),
    "Más de 3.5 tarjetas": ("t", 3.5, "o"),
    "Menos de 3.5 tarjetas": ("t", 3.5, "u"),
    "Más de 4.5 tarjetas": ("t", 4.5, "o"),
    "Menos de 4.5 tarjetas": ("t", 4.5, "u"),
    "Menos de 5.5 tarjetas": ("t", 5.5, "u"),
    "Más de 13.5 saques de meta": ("s", 13.5, "o"),
    "Menos de 13.5 saques de meta": ("s", 13.5, "u"),
    "Más de 15.5 saques de meta": ("s", 15.5, "o"),
    "Menos de 15.5 saques de meta": ("s", 15.5, "u"),
    "Más de 17.5 saques de meta": ("s", 17.5, "o"),
    "Menos de 17.5 saques de meta": ("s", 17.5, "u"),
}

FAMILIAS_PARLEY = {
    "Resultado": ["Gana local", "Gana visita", "Local o empate (1X)", "Empate o visita (X2)", "Local o visita, no empate (12)"],
    "Goles totales": ["Más de 1.5 goles", "Menos de 1.5 goles", "Más de 2.5 goles", "Menos de 2.5 goles", "Más de 3.5 goles", "Menos de 3.5 goles", "Menos de 4.5 goles"],
    "Ambos anotan": ["Ambos anotan", "No ambos anotan"],
    "Primer gol": ["Primer gol: local", "Primer gol: visita"],
    "Córners": [k for k in MERCADOS_COMBI if "córners" in k],
    "Tarjetas": [k for k in MERCADOS_COMBI if "tarjetas" in k],
    "Saques de meta": [k for k in MERCADOS_COMBI if "saques" in k],
}

FAMILIAS_BB = dict(FAMILIAS_PARLEY)
FAMILIAS_BB["Goles local"] = ["Local marca +0.5", "Local marca +1.5"]
FAMILIAS_BB["Goles visita"] = ["Visita marca +0.5", "Visita marca +1.5"]


def prob_partido_combi(a, mercados) -> tuple[float, float]:
    goles = [m[1] for m in mercados if m[0] == "g"]
    p_corr = prob_conjunta(a.matriz, goles) if goles else 1.0
    p_naive = 1.0
    for g in goles:
        p_naive *= prob_marginal(a.matriz, g)
    extra = 1.0
    for m in mercados:
        if m[0] == "c" and a.corners_esp:
            ov = over_under(a.corners_esp, [m[1]])[m[1]]
            extra *= ov if m[2] == "o" else (1 - ov)
        elif m[0] == "t" and a.tarjetas_esp:
            ov = over_under_nb(a.tarjetas_esp, a.tarjetas_ratio_var, [m[1]])[m[1]]
            extra *= ov if m[2] == "o" else (1 - ov)
        elif m[0] == "s" and a.saques_local and a.saques_visita:
            ov = over_under(a.saques_local + a.saques_visita, [m[1]])[m[1]]
            extra *= ov if m[2] == "o" else (1 - ov)
        elif m[0] == "pg":
            pl, pv, sin = primer_gol(a.lh, a.la, float(a.matriz[0, 0]))
            extra *= {"l": pl, "v": pv, "n": sin}[m[1]]
    return p_corr * extra, p_naive * extra


def prob_individual(a, spec) -> float:
    if spec[0] == "g":
        return prob_marginal(a.matriz, spec[1])
    if spec[0] == "c" and a.corners_esp:
        ov = over_under(a.corners_esp, [spec[1]])[spec[1]]
        return ov if spec[2] == "o" else 1 - ov
    if spec[0] == "t" and a.tarjetas_esp:
        ov = over_under_nb(a.tarjetas_esp, a.tarjetas_ratio_var, [spec[1]])[spec[1]]
        return ov if spec[2] == "o" else 1 - ov
    if spec[0] == "s" and a.saques_local and a.saques_visita:
        ov = over_under(a.saques_local + a.saques_visita, [spec[1]])[spec[1]]
        return ov if spec[2] == "o" else 1 - ov
    if spec[0] == "pg":
        pl, pv, sin = primer_gol(a.lh, a.la, float(a.matriz[0, 0]))
        return {"l": pl, "v": pv, "n": sin}[spec[1]]
    return 1.0


def desglose(pares) -> pd.DataFrame:
    acum = 1.0
    filas = []
    for nombre, prob in pares:
        acum *= prob
        filas.append({"Selección": nombre, "Probabilidad": pct(prob), "Prob. acumulada": pct(acum)})
    return pd.DataFrame(filas)


def parley_sugerido(a, umbral: float = 0.68) -> list[tuple[str, float]]:
    seleccion = []
    for claves in FAMILIAS_PARLEY.values():
        cand = [(c, prob_individual(a, MERCADOS_COMBI[c])) for c in claves if c in MERCADOS_COMBI]
        cand = [(c, p) for c, p in cand if p >= umbral]
        if cand:
            seleccion.append(max(cand, key=lambda x: x[1]))
    return seleccion


def armar_bb_partido(a, cuota_min: float, total_min: float, n_min: int):
    cand = []
    for claves in FAMILIAS_BB.values():
        ops = [(c, prob_individual(a, MERCADOS_COMBI[c])) for c in claves if c in MERCADOS_COMBI]
        ops = [(c, p) for c, p in ops if p > 0 and 1 / p > cuota_min]
        if ops:
            cand.append(max(ops, key=lambda x: x[1]))
    cand.sort(key=lambda x: -x[1])
    sel, prob, cuota = [], 0.0, 0.0
    for nombre, _p in cand:
        sel.append(nombre)
        prob, _ = prob_partido_combi(a, [MERCADOS_COMBI[x] for x in sel])
        cuota = 1 / prob if prob > 0 else 0
        if len(sel) >= n_min and cuota > total_min:
            break
    filas = [{"Mercado": m, "Probabilidad": pct(prob_individual(a, MERCADOS_COMBI[m])),
              "Cuota justa": f"{1 / prob_individual(a, MERCADOS_COMBI[m]):.2f}"} for m in sel]
    return filas, prob, cuota, len(sel), a.fiable


def armar_bb_varios(cfg: Config, liga_codigo: str, prox, cuota_min: float, total_min: float, n_min: int):
    conn = connect(cfg.db_path)
    cand = []
    for p in prox:
        a = analizar_club(conn, cfg.data_dir, liga_codigo, p["lf"], p["vf"])
        if a is None:
            continue
        ops = [(nombre, prob_individual(a, spec)) for nombre, spec in MERCADOS_COMBI.items()]
        ops = [(nombre, pr) for nombre, pr in ops if 0 < pr < 0.667 and 1 / pr > cuota_min]
        if ops:
            best = max(ops, key=lambda x: x[1])
            cand.append({"Partido": f"{a.nombre_local} vs {a.nombre_visita}", "Mercado": best[0], "p": best[1], "fiable": a.fiable})
    conn.close()
    cand.sort(key=lambda x: -x["p"])
    sel, prob = [], 1.0
    for c in cand:
        sel.append(c)
        prob *= c["p"]
        if len(sel) >= n_min and 1 / prob > total_min:
            break
    cuota = 1 / prob if prob > 0 else 0
    fiable = all(c["fiable"] for c in sel)
    filas = [{"Partido": c["Partido"], "Mercado": c["Mercado"], "Probabilidad": pct(c["p"]), "Cuota justa": f"{1 / c['p']:.2f}"} for c in sel]
    return filas, prob, cuota, len(sel), fiable
