from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson


@dataclass
class Ajustes:
    ataque_local: float = 1.0
    defensa_local: float = 1.0
    ataque_visita: float = 1.0
    defensa_visita: float = 1.0


@dataclass
class ParametrosModelo:
    tasa_base: float
    beta_elo: float = 0.20
    rho: float = -0.08
    ventaja_local_elo: float = 0.0
    max_goles: int = 10


def lambdas(elo_local: float, elo_visita: float, par: ParametrosModelo, aj: Ajustes) -> tuple[float, float]:
    dr = (elo_local - elo_visita + par.ventaja_local_elo) / 100.0
    lh = par.tasa_base * np.exp(par.beta_elo * dr) * aj.ataque_local * aj.defensa_visita
    la = par.tasa_base * np.exp(-par.beta_elo * dr) * aj.ataque_visita * aj.defensa_local
    return float(lh), float(la)


def matriz_marcadores(lh: float, la: float, par: ParametrosModelo) -> np.ndarray:
    rango = np.arange(par.max_goles + 1)
    m = np.outer(poisson.pmf(rango, lh), poisson.pmf(rango, la))
    r = par.rho
    m[0, 0] *= 1 - lh * la * r
    m[0, 1] *= 1 + lh * r
    m[1, 0] *= 1 + la * r
    m[1, 1] *= 1 - r
    m = np.clip(m, 0.0, None)
    return m / m.sum()


def corregir_empate_matriz(m: np.ndarray, delta: float) -> np.ndarray:
    if delta == 0.0:
        return m
    px = float(np.trace(m))
    resto = 1.0 - px
    objetivo = min(max(px - delta, 1e-6), 1.0 - 1e-6)
    if px <= 0.0 or resto <= 0.0:
        return m
    out = m.copy()
    diag = np.eye(m.shape[0], dtype=bool)
    out[diag] *= objetivo / px
    out[~diag] *= (1.0 - objetivo) / resto
    return out


def mercados(m: np.ndarray) -> dict[str, float]:
    n = m.shape[0]
    total = np.add.outer(np.arange(n), np.arange(n))
    btts = float(m[1:, 1:].sum())
    return {
        "1": float(np.tril(m, -1).sum()),
        "X": float(np.trace(m)),
        "2": float(np.triu(m, 1).sum()),
        "over25": float(m[total > 2].sum()),
        "under25": float(m[total <= 2].sum()),
        "btts_si": btts,
        "btts_no": 1.0 - btts,
    }
