from __future__ import annotations

import math

import numpy as np

from src.config import Config
from src.ui.datos import params_corners


def pct(x) -> str:
    return f"{x * 100:.1f}%" if x is not None else "—"


def dist_goles(matriz: np.ndarray) -> np.ndarray:
    n = matriz.shape[0]
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    return np.bincount((i + j).ravel(), weights=matriz.ravel())


def p_over_linea(dist: np.ndarray, linea: float) -> float:
    n = int(math.floor(linea))
    frac = round(linea - n, 2)
    over = float(dist[n + 1:].sum())
    under = float(dist[:n].sum())

    def nopush(o, u):
        return o / (o + u) if (o + u) > 0 else 0.5

    if frac == 0.5:
        return over
    if frac == 0.0:
        return nopush(over, under)
    if frac == 0.25:
        return 0.5 * (nopush(over, under) + over)
    if frac == 0.75:
        over1 = float(dist[n + 2:].sum())
        under1 = float(dist[:n + 1].sum())
        return 0.5 * (over + nopush(over1, under1))
    return over


def estilo_texto(p: dict) -> str:
    if p.get("estilo"):
        return p["estilo"]
    xg, xga = p.get("xg_fs"), p.get("xga_fs")
    if not xg or not xga:
        return "estilo no disponible"
    rasgos = []
    if xg >= 1.9:
        rasgos.append("muy ofensivo")
    elif xg >= 1.5:
        rasgos.append("ofensivo")
    elif xg < 1.1:
        rasgos.append("conservador en ataque")
    if xga <= 0.8:
        rasgos.append("sólido en defensa")
    elif xga >= 1.4:
        rasgos.append("frágil atrás")
    if xg + xga >= 3.0:
        rasgos.append("partidos abiertos")
    elif xg + xga <= 2.0:
        rasgos.append("partidos cerrados")
    return ", ".join(rasgos) if rasgos else "equilibrado"


def over_equipo(matriz: np.ndarray, eje: int, linea: float) -> float:
    marg = matriz.sum(axis=1) if eje == 0 else matriz.sum(axis=0)
    return float(marg[int(linea) + 1:].sum())


def primer_gol(lh: float, la: float, p00: float) -> tuple[float, float, float]:
    tot = lh + la
    if tot <= 0:
        return 0.0, 0.0, 1.0
    return (lh / tot) * (1 - p00), (la / tot) * (1 - p00), p00


def corners_equipo(cfg: Config, a) -> tuple[float | None, float | None]:
    if not a.corners_esp or (a.lh + a.la) <= 0:
        return None, None
    a0, b = params_corners(cfg)
    share = min(0.85, max(0.15, a0 + b * (a.lh / (a.lh + a.la))))
    return a.corners_esp * share, a.corners_esp * (1 - share)
