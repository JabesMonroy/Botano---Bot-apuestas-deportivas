from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from src.modelo.dixon_coles import Ajustes

HALF_LIFE = 1.5
ARCHIVO = "fuerzas.json"


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _filas_historico(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT fecha, home_api_id h, away_api_id a, goles_home gh, goles_away ga FROM historico "
        "WHERE home_api_id IS NOT NULL AND away_api_id IS NOT NULL "
        "AND goles_home IS NOT NULL AND goles_away IS NOT NULL"
    ).fetchall()


def construir_dataset(filas, min_partidos: int = 5, ref: datetime | None = None):
    cnt: Counter = Counter()
    for r in filas:
        cnt[r["h"]] += 1
        cnt[r["a"]] += 1
    validos = {t for t, c in cnt.items() if c >= min_partidos}
    filas = [r for r in filas if r["h"] in validos and r["a"] in validos]

    equipos = sorted({r["h"] for r in filas} | {r["a"] for r in filas})
    idx = {t: i for i, t in enumerate(equipos)}
    fechas = [_parse(r["fecha"]) for r in filas]
    if ref is None:
        ref = max(f for f in fechas if f)
    xi = math.log(2) / HALF_LIFE

    h = np.array([idx[r["h"]] for r in filas])
    a = np.array([idx[r["a"]] for r in filas])
    gh = np.array([r["gh"] for r in filas], dtype=float)
    ga = np.array([r["ga"] for r in filas], dtype=float)
    dt = np.array([(ref - f).days / 365.25 if f else 5.0 for f in fechas])
    w = np.exp(-xi * dt)
    return equipos, h, a, gh, ga, w, ref


def cargar_partidos(conn: sqlite3.Connection, min_partidos: int = 5):
    return construir_dataset(_filas_historico(conn), min_partidos)


def ajustar(equipos: list[int], h, a, gh, ga, w, reg: float = 0.01) -> dict:
    n = len(equipos)
    gln = gammaln(gh + 1) + gammaln(ga + 1)
    m00 = (gh == 0) & (ga == 0)
    m01 = (gh == 0) & (ga == 1)
    m10 = (gh == 1) & (ga == 0)
    m11 = (gh == 1) & (ga == 1)

    def negll(theta):
        al, be = theta[:n], theta[n : 2 * n]
        mu, gamma, rho = theta[2 * n], theta[2 * n + 1], theta[2 * n + 2]
        loglh = mu + gamma + al[h] - be[a]
        logla = mu + al[a] - be[h]
        lh, la = np.exp(loglh), np.exp(logla)
        ll = gh * loglh - lh + ga * logla - la - gln
        tau = np.ones_like(lh)
        tau[m00] = 1 - lh[m00] * la[m00] * rho
        tau[m01] = 1 + lh[m01] * rho
        tau[m10] = 1 + la[m10] * rho
        tau[m11] = 1 - rho
        ll = ll + np.log(np.clip(tau, 1e-9, None))
        return -np.sum(w * ll) + reg * (np.sum(al * al) + np.sum(be * be))

    theta0 = np.zeros(2 * n + 3)
    theta0[2 * n] = math.log(1.3)
    theta0[2 * n + 1] = 0.25
    theta0[2 * n + 2] = -0.05
    bounds = [(-3, 3)] * (2 * n) + [(-2, 2), (-1, 1), (-0.2, 0.2)]
    res = minimize(negll, theta0, method="L-BFGS-B", bounds=bounds)

    al, be = res.x[:n], res.x[n : 2 * n]
    mu, gamma, rho = res.x[2 * n], res.x[2 * n + 1], res.x[2 * n + 2]
    media = float(np.mean(al))
    al = al - media
    mu = mu + media
    fuerzas = {str(equipos[i]): {"ataque": float(al[i]), "defensa": float(be[i])} for i in range(n)}
    return {"fuerzas": fuerzas, "mu": float(mu), "gamma": float(gamma), "rho": float(rho)}


def guardar(data_dir: Path, params: dict, ref: datetime) -> None:
    ruta = data_dir / "modelos" / ARCHIVO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = dict(params)
    datos["fecha_ref"] = ref.isoformat()
    datos["half_life"] = HALF_LIFE
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar(data_dir: Path) -> dict | None:
    ruta = data_dir / "modelos" / ARCHIVO
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def lambdas_desde_fuerzas(api_h: int, api_a: int, f: dict, aj: Ajustes, ventaja_local: float = 0.0):
    fz = f["fuerzas"]
    kh, ka = str(api_h), str(api_a)
    if kh not in fz or ka not in fz:
        return None
    loglh = f["mu"] + ventaja_local + fz[kh]["ataque"] - fz[ka]["defensa"]
    logla = f["mu"] + fz[ka]["ataque"] - fz[kh]["defensa"]
    lh = math.exp(loglh) * aj.ataque_local * aj.defensa_visita
    la = math.exp(logla) * aj.ataque_visita * aj.defensa_local
    return lh, la
