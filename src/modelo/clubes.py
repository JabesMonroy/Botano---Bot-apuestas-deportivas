from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from src.modelo.dixon_coles import ParametrosModelo, matriz_marcadores

VIDA_MEDIA_DIAS = 365.0
PESO_XG = 0.7


def _pesos(fechas: list[datetime], ref: datetime) -> np.ndarray:
    dias = np.array([(ref - f).days for f in fechas], dtype=float)
    return np.exp(-math.log(2.0) / VIDA_MEDIA_DIAS * np.clip(dias, 0.0, None))


def construir_dataset(filas: list[dict], ref: datetime, usar_xg: bool = True):
    equipos = sorted({f["local"] for f in filas} | {f["visita"] for f in filas})
    idx = {e: i for i, e in enumerate(equipos)}
    h = np.array([idx[f["local"]] for f in filas])
    a = np.array([idx[f["visita"]] for f in filas])

    def objetivo(f, lado: str) -> float:
        goles = float(f[f"goles_{lado}"])
        xg = f.get(f"xg_{lado}")
        if usar_xg and xg is not None:
            return PESO_XG * float(xg) + (1.0 - PESO_XG) * goles
        return goles

    gh = np.array([objetivo(f, "local") for f in filas])
    ga = np.array([objetivo(f, "visita") for f in filas])
    fechas = [datetime.fromisoformat(f["fecha"]) for f in filas]
    w = _pesos(fechas, ref)
    return equipos, h, a, gh, ga, w


def ajustar(equipos, h, a, gh, ga, w, reg: float = 0.02) -> dict:
    n = len(equipos)

    def neg_log_lik(x):
        mu, gamma = x[0], x[1]
        atk, dfn = x[2 : 2 + n], x[2 + n :]
        llh = mu + gamma + atk[h] - dfn[a]
        lla = mu + atk[a] - dfn[h]
        lh, la = np.exp(llh), np.exp(lla)
        ll = w * (gh * llh - lh + ga * lla - la)
        return -ll.sum() + reg * (atk @ atk + dfn @ dfn) * w.sum() / n

    x0 = np.zeros(2 + 2 * n)
    x0[0] = math.log(max(gh.mean(), 0.2))
    res = minimize(neg_log_lik, x0, method="L-BFGS-B", options={"maxiter": 600})
    mu, gamma = float(res.x[0]), float(res.x[1])
    atk, dfn = res.x[2 : 2 + n], res.x[2 + n :]
    return {
        "mu": mu + float(atk.mean()) - float(dfn.mean()),
        "gamma": gamma,
        "rho": _ajustar_rho(mu, gamma, atk, dfn, h, a, gh, ga, w),
        "equipos": {e: {"ataque": float(atk[i] - atk.mean()), "defensa": float(dfn[i] - dfn.mean())} for i, e in enumerate(equipos)},
    }


def _ajustar_rho(mu, gamma, atk, dfn, h, a, gh, ga, w) -> float:
    gh_int = np.round(gh).astype(int)
    ga_int = np.round(ga).astype(int)
    lh = np.exp(mu + gamma + atk[h] - dfn[a])
    la = np.exp(mu + atk[a] - dfn[h])
    mejor, mejor_ll = 0.0, -np.inf
    for rho in np.arange(-0.28, 0.01, 0.02):
        tau = np.ones(len(gh_int))
        m00 = (gh_int == 0) & (ga_int == 0)
        m01 = (gh_int == 0) & (ga_int == 1)
        m10 = (gh_int == 1) & (ga_int == 0)
        m11 = (gh_int == 1) & (ga_int == 1)
        tau[m00] = 1.0 - lh[m00] * la[m00] * rho
        tau[m01] = 1.0 + lh[m01] * rho
        tau[m10] = 1.0 + la[m10] * rho
        tau[m11] = 1.0 - rho
        if (tau <= 0).any():
            continue
        ll = (w * np.log(tau)).sum()
        if ll > mejor_ll:
            mejor_ll, mejor = ll, float(rho)
    return mejor


def cargar(data_dir: Path, codigo: str) -> dict | None:
    ruta = data_dir / "modelos" / f"fuerzas_club_{codigo}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def lambdas(params: dict, local: str, visita: str) -> tuple[float, float] | None:
    eq = params["equipos"]
    if local not in eq or visita not in eq:
        return None
    lh = math.exp(params["mu"] + params["gamma"] + eq[local]["ataque"] - eq[visita]["defensa"])
    la = math.exp(params["mu"] + eq[visita]["ataque"] - eq[local]["defensa"])
    return lh, la


def probabilidades(params: dict, local: str, visita: str) -> dict | None:
    res = lambdas(params, local, visita)
    if res is None:
        return None
    lh, la = res
    m = matriz_marcadores(lh, la, ParametrosModelo(tasa_base=0.0, rho=params["rho"]))
    n = m.shape[0]
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    dist = np.bincount((i + j).ravel(), weights=m.ravel())
    return {
        "1": float(np.tril(m, -1).sum()),
        "X": float(np.trace(m)),
        "2": float(np.triu(m, 1).sum()),
        "over25": float(dist[3:].sum()),
        "btts": float(1.0 - m[0, :].sum() - m[:, 0].sum() + m[0, 0]),
        "lambdas": (lh, la),
    }
