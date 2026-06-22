from __future__ import annotations

import numpy as np

PREDICADOS = {
    "1": lambda i, j: i > j,
    "X": lambda i, j: i == j,
    "2": lambda i, j: i < j,
    "1X": lambda i, j: i >= j,
    "12": lambda i, j: i != j,
    "X2": lambda i, j: i <= j,
    "over0.5": lambda i, j: i + j >= 1,
    "under0.5": lambda i, j: i + j <= 0,
    "over1.5": lambda i, j: i + j >= 2,
    "under1.5": lambda i, j: i + j <= 1,
    "over2.5": lambda i, j: i + j >= 3,
    "under2.5": lambda i, j: i + j <= 2,
    "over3.5": lambda i, j: i + j >= 4,
    "under3.5": lambda i, j: i + j <= 3,
    "over4.5": lambda i, j: i + j >= 5,
    "under4.5": lambda i, j: i + j <= 4,
    "loc0.5": lambda i, j: i >= 1,
    "loc1.5": lambda i, j: i >= 2,
    "loc2.5": lambda i, j: i >= 3,
    "vis0.5": lambda i, j: j >= 1,
    "vis1.5": lambda i, j: j >= 2,
    "vis2.5": lambda i, j: j >= 3,
    "btts": lambda i, j: (i >= 1) & (j >= 1),
    "nobtts": lambda i, j: (i < 1) | (j < 1),
}


def _ij(n: int):
    return np.meshgrid(np.arange(n), np.arange(n), indexing="ij")


def prob_marginal(matriz: np.ndarray, nombre: str) -> float:
    i, j = _ij(matriz.shape[0])
    return float(matriz[PREDICADOS[nombre](i, j)].sum())


def prob_conjunta(matriz: np.ndarray, nombres: list[str]) -> float:
    i, j = _ij(matriz.shape[0])
    mascara = np.ones(matriz.shape, dtype=bool)
    for nb in nombres:
        mascara &= PREDICADOS[nb](i, j)
    return float(matriz[mascara].sum())
