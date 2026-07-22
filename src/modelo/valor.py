from __future__ import annotations


def sin_vig(cuotas: dict[str, float]) -> dict[str, float]:
    inv = {k: 1.0 / v for k, v in cuotas.items()}
    s = sum(inv.values())
    if s <= 1.0 or any(p >= 1.0 for p in inv.values()):
        return {k: v / s for k, v in inv.items()}
    lo, hi = 1.0, 5.0
    for _ in range(60):
        k = (lo + hi) / 2.0
        if sum(p**k for p in inv.values()) > 1.0:
            lo = k
        else:
            hi = k
    pot = {c: p ** ((lo + hi) / 2.0) for c, p in inv.items()}
    t = sum(pot.values())
    return {c: p / t for c, p in pot.items()}


def ev(prob: float, cuota: float) -> float:
    return prob * (cuota - 1.0) - (1.0 - prob)


def kelly(prob: float, cuota: float, fraccion: float = 0.25, tope: float = 0.03) -> float:
    b = cuota - 1.0
    if b <= 0:
        return 0.0
    f = (prob * b - (1.0 - prob)) / b
    return min(max(f, 0.0) * fraccion, tope)


def corregir_empate(p1: float, px: float, p2: float, delta: float) -> tuple[float, float, float]:
    nx = max(px - delta, 1e-6)
    quitado = px - nx
    s = p1 + p2
    if s <= 0:
        return p1, nx, p2
    return p1 + quitado * p1 / s, nx, p2 + quitado * p2 / s


def mezclar_1x2(modelo: dict[str, float], mercado: dict[str, float], w_mercado: float) -> dict[str, float]:
    return {k: (1.0 - w_mercado) * modelo[k] + w_mercado * mercado[k] for k in ("1", "X", "2")}
