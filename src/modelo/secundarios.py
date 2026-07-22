from __future__ import annotations

from scipy.stats import nbinom, poisson


def over_under(lam: float, lineas: list[float]) -> dict[float, float]:
    return {linea: float(1.0 - poisson.cdf(int(linea), lam)) for linea in lineas}


def over_under_nb(mu: float, ratio_var: float, lineas: list[float]) -> dict[float, float]:
    if ratio_var <= 1.0:
        return over_under(mu, lineas)
    r = mu / (ratio_var - 1.0)
    p = r / (r + mu)
    return {linea: float(1.0 - nbinom.cdf(int(linea), r, p)) for linea in lineas}
