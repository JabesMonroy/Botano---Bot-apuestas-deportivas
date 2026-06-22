from __future__ import annotations

import json
import math
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from src.modelo.dixon_coles import Ajustes
from src.scrapers.eloratings import EloRatings

HALF_LIFE = 1.5
ARCHIVO = "fuerzas.json"


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def _filas_historico(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT fecha, home_api_id h, away_api_id a, goles_home gh, goles_away ga FROM historico "
        "WHERE home_api_id IS NOT NULL AND away_api_id IS NOT NULL "
        "AND goles_home IS NOT NULL AND goles_away IS NOT NULL"
    ).fetchall()


def mapa_elo(conn: sqlite3.Connection, cache_dir: Path) -> dict[int, float]:
    idx: dict[str, float] = {}
    for _code, nombre, elo, alias in EloRatings(cache_dir / "eloratings").ratings():
        for n in (nombre, *alias):
            idx.setdefault(_norm(n), float(elo))
    api_nombre: dict[int, str] = {}
    for r in conn.execute(
        "SELECT home_api_id id, home_name n FROM historico WHERE home_api_id IS NOT NULL "
        "UNION SELECT away_api_id, away_name FROM historico WHERE away_api_id IS NOT NULL"
    ):
        api_nombre[r["id"]] = r["n"]
    return {api_id: idx[_norm(n)] for api_id, n in api_nombre.items() if _norm(n) in idx}


def construir_dataset(filas, elo_por_api: dict[int, float], min_partidos: int = 5, ref: datetime | None = None):
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

    elos = [elo_por_api.get(t) for t in equipos]
    presentes = [e for e in elos if e is not None]
    media = sum(presentes) / len(presentes) if presentes else 1500.0
    elo_norm = np.array([((e if e is not None else media) - media) / 100.0 for e in elos])
    return equipos, h, a, gh, ga, w, elo_norm, ref


def cargar_partidos(conn: sqlite3.Connection, cache_dir: Path, min_partidos: int = 5):
    return construir_dataset(_filas_historico(conn), mapa_elo(conn, cache_dir), min_partidos)


def ajustar(equipos, h, a, gh, ga, w, elo_norm, reg: float = 0.05) -> dict:
    n = len(equipos)
    gln = gammaln(gh + 1) + gammaln(ga + 1)
    m00 = (gh == 0) & (ga == 0)
    m01 = (gh == 0) & (ga == 1)
    m10 = (gh == 1) & (ga == 0)
    m11 = (gh == 1) & (ga == 1)
    ed = elo_norm

    def negll(theta):
        al, be = theta[:n], theta[n : 2 * n]
        mu, gamma, rho, th = theta[2 * n], theta[2 * n + 1], theta[2 * n + 2], theta[2 * n + 3]
        d = th * (ed[h] - ed[a])
        loglh = mu + gamma + d + al[h] - be[a]
        logla = mu - d + al[a] - be[h]
        lh, la = np.exp(loglh), np.exp(logla)
        ll = gh * loglh - lh + ga * logla - la - gln
        tau = np.ones_like(lh)
        tau[m00] = 1 - lh[m00] * la[m00] * rho
        tau[m01] = 1 + lh[m01] * rho
        tau[m10] = 1 + la[m10] * rho
        tau[m11] = 1 - rho
        ll = ll + np.log(np.clip(tau, 1e-9, None))
        return -np.sum(w * ll) + reg * (np.sum(al * al) + np.sum(be * be))

    theta0 = np.zeros(2 * n + 4)
    theta0[2 * n] = math.log(1.3)
    theta0[2 * n + 1] = 0.25
    theta0[2 * n + 2] = -0.05
    theta0[2 * n + 3] = 0.30
    bounds = [(-3, 3)] * (2 * n) + [(-2, 2), (-1, 1), (-0.2, 0.2), (0.0, 2.0)]
    res = minimize(negll, theta0, method="L-BFGS-B", bounds=bounds)

    al, be = res.x[:n], res.x[n : 2 * n]
    mu, gamma, rho, th = res.x[2 * n], res.x[2 * n + 1], res.x[2 * n + 2], res.x[2 * n + 3]
    media = float(np.mean(al))
    al = al - media
    mu = mu + media
    fuerzas = {
        str(equipos[i]): {"ataque": float(al[i]), "defensa": float(be[i]), "e": float(ed[i])}
        for i in range(n)
    }
    return {"fuerzas": fuerzas, "mu": float(mu), "gamma": float(gamma), "rho": float(rho), "theta": float(th)}


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
    th, tv, txg = f.get("theta", 0.0), f.get("theta_valor", 0.0), f.get("theta_xg", 0.0)
    eh, ea = fz[kh].get("e", 0.0), fz[ka].get("e", 0.0)
    wh, wa = fz[kh].get("w", 0.0), fz[ka].get("w", 0.0)
    sxh, sxa = fz[kh].get("sx", 0.0), fz[ka].get("sx", 0.0)
    d = th * (eh - ea) + tv * (wh - wa) + txg * (sxh - sxa)
    loglh = f["mu"] + ventaja_local + d + fz[kh]["ataque"] - fz[ka]["defensa"]
    logla = f["mu"] - d + fz[ka]["ataque"] - fz[kh]["defensa"]
    lh = math.exp(loglh) * aj.ataque_local * aj.defensa_visita
    la = math.exp(logla) * aj.ataque_visita * aj.defensa_local
    return lh, la
