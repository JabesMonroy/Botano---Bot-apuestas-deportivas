from __future__ import annotations


def sin_vig(cuotas: dict[str, float]) -> dict[str, float]:
    inv = {k: 1.0 / v for k, v in cuotas.items()}
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()}


def ev(prob: float, cuota: float) -> float:
    return prob * (cuota - 1.0) - (1.0 - prob)
