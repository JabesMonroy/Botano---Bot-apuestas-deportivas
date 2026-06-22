from __future__ import annotations

from scipy.stats import poisson


def over_under(lam: float, lineas: list[float]) -> dict[float, float]:
    return {linea: float(1.0 - poisson.cdf(int(linea), lam)) for linea in lineas}
