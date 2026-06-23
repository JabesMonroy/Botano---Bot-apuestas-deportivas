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


def prob_over(api_h: int, api_a: int, params: dict, lineas, ventaja: float = 0.0):
    import numpy as np
    res = lambdas_desde_fuerzas(api_h, api_a, params, Ajustes(), ventaja_local=ventaja)
    if res is None:
        return None
    lh, la = res
    m = matriz_marcadores(lh, la, ParametrosModelo(tasa_base=0.0, rho=params["rho"]))
    n = m.shape[0]
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    dist = np.bincount((i + j).ravel(), weights=m.ravel())
    return {L: float(dist[int(L) + 1:].sum()) for L in lineas}


def calibracion_bin(registros, nbins: int = 10):
    sump = [0.0] * nbins
    sumo = [0.0] * nbins
    cnt = [0] * nbins
    for p, o in registros:
        b = min(nbins - 1, int(p * nbins))
        sump[b] += p
        sumo[b] += o
        cnt[b] += 1
    return [{"rango": f"{b * 100 // nbins}-{(b + 1) * 100 // nbins}%", "predicha": round(sump[b] / cnt[b], 4),
             "observada": round(sumo[b] / cnt[b], 4), "n": cnt[b]} for b in range(nbins) if cnt[b]]


def brier_bin(registros) -> float:
    return sum((p - o) ** 2 for p, o in registros) / len(registros) if registros else float("nan")


def media(xs) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def estrato(p) -> str:
    fav = max(p[0], p[2])
    if fav >= 0.60:
        return "facil"
    if fav < 0.45:
        return "renido"
    return "medio"


def calibracion(registros, nbins: int = 10):
    sump = [0.0] * nbins
    sumo = [0.0] * nbins
    cnt = [0] * nbins
    for p, o in registros:
        for k in range(3):
            b = min(nbins - 1, int(p[k] * nbins))
            sump[b] += p[k]
            sumo[b] += 1.0 if o == k else 0.0
            cnt[b] += 1
    filas = []
    for b in range(nbins):
        if cnt[b]:
            filas.append({
                "rango": f"{b * 100 // nbins}-{(b + 1) * 100 // nbins}%",
                "predicha": round(sump[b] / cnt[b], 4),
                "observada": round(sumo[b] / cnt[b], 4),
                "n": cnt[b],
            })
    return filas


def ece(registros, nbins: int = 10) -> float:
    cal = calibracion(registros, nbins)
    tot = sum(f["n"] for f in cal)
    return sum(f["n"] * abs(f["predicha"] - f["observada"]) for f in cal) / tot if tot else float("nan")


def brier(registros) -> float:
    s = 0.0
    n = 0
    for p, o in registros:
        s += sum((p[k] - (1.0 if o == k else 0.0)) ** 2 for k in range(3))
        n += 1
    return s / n if n else float("nan")
