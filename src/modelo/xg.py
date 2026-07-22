from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ARCHIVO = "xg_disparo.json"
XG_PENAL = 0.76
LARGO_M = 105.0
ANCHO_M = 68.0
ARCO_M = 7.32


def geometria(mx: float, my: float) -> tuple[float, float]:
    dx = LARGO_M - mx
    dy = my - ANCHO_M / 2.0
    dist = math.hypot(dx, dy)
    ang = math.atan2(ARCO_M * dx, dx * dx + dy * dy - (ARCO_M / 2.0) ** 2)
    return dist, max(ang, 0.0)


def desde_statsbomb(x: float, y: float) -> tuple[float, float]:
    return geometria(x * LARGO_M / 120.0, y * ANCHO_M / 80.0)


def desde_whoscored(x: float, y: float) -> tuple[float, float]:
    return geometria(x * LARGO_M / 100.0, y * ANCHO_M / 100.0)


def _matriz(dist, ang, cabeza) -> np.ndarray:
    dist = np.asarray(dist, dtype=float)
    return np.column_stack([
        np.ones(len(dist)),
        np.log(np.clip(dist, 0.5, None)),
        np.asarray(ang, dtype=float),
        np.asarray(cabeza, dtype=float),
    ])


def ajustar_logistico(dist, ang, cabeza, gol) -> list[float]:
    X = _matriz(dist, ang, cabeza)
    y = np.asarray(gol, dtype=float)

    def nll(b):
        z = X @ b
        return float(np.sum(np.logaddexp(0.0, z) - y * z))

    res = minimize(nll, np.zeros(X.shape[1]), method="BFGS")
    return [float(v) for v in res.x]


def prob_gol(coefs: list[float], dist: float, ang: float, cabeza: bool, penal: bool = False) -> float:
    if penal:
        return XG_PENAL
    z = coefs[0] + coefs[1] * math.log(max(dist, 0.5)) + coefs[2] * ang + coefs[3] * (1.0 if cabeza else 0.0)
    return 1.0 / (1.0 + math.exp(-z))


def guardar(data_dir: Path, coefs: list[float], meta: dict) -> None:
    ruta = data_dir / "modelos" / ARCHIVO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"coefs": coefs, **meta}, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar(data_dir: Path) -> dict | None:
    ruta = data_dir / "modelos" / ARCHIVO
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
