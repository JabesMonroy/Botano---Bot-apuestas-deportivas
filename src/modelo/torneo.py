from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.modelo.dixon_coles import Ajustes, ParametrosModelo, lambdas, matriz_marcadores
from src.modelo.fuerzas import cargar as cargar_fuerzas
from src.modelo.fuerzas import lambdas_desde_fuerzas
from src.modelo.parametros import HOSTS
from src.modelo.parametros import cargar as cargar_par


def _matriz(eqh, eqa, fuerzas, par_elo, ventaja):
    aj = Ajustes()
    res = None
    if fuerzas and eqh["api_football_id"] and eqa["api_football_id"]:
        res = lambdas_desde_fuerzas(eqh["api_football_id"], eqa["api_football_id"], fuerzas, aj, ventaja_local=ventaja)
    if res is None:
        if eqh["elo"] is None or eqa["elo"] is None:
            return None
        lh, la = lambdas(eqh["elo"], eqa["elo"], par_elo, aj)
        rho = par_elo.rho
    else:
        lh, la = res
        rho = fuerzas["rho"]
    return matriz_marcadores(lh, la, ParametrosModelo(tasa_base=0.0, rho=rho))


def _prep(matriz: np.ndarray):
    return np.cumsum(matriz.ravel()), matriz.shape[0]


def _sample(cum, n, u):
    return divmod(int(np.searchsorted(cum, u * cum[-1])), n)


class CacheEliminatoria:
    def __init__(self, eq, fuerzas, par_elo):
        self._eq, self._f, self._p, self._d = eq, fuerzas, par_elo, {}

    def _entry(self, a, b):
        key = (a, b) if a < b else (b, a)
        if key not in self._d:
            x, y = key
            m = _matriz(self._eq[x], self._eq[y], self._f, self._p, 0.0)
            n = m.shape[0]
            i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
            self._d[key] = (np.cumsum(m.ravel()), n, float(m[i > j].sum()), float(m[i < j].sum()))
        return key, self._d[key]

    def ganador(self, a, b, rng):
        key, (cum, n, ph, pa) = self._entry(a, b)
        x, y = key
        gi, gj = _sample(cum, n, rng.random())
        if gi > gj:
            return x
        if gi < gj:
            return y
        total = ph + pa
        return x if (total > 0 and rng.random() < ph / total) else y


def cargar_estado(conn: sqlite3.Connection, data_dir: Path):
    fuerzas = cargar_fuerzas(data_dir)
    par_elo = cargar_par(data_dir, conn)
    eq = {
        r["api_football_id"]: r
        for r in conn.execute("SELECT api_football_id, fifa_code, nombre, elo FROM equipos WHERE api_football_id IS NOT NULL")
    }
    base, grupos = {}, defaultdict(list)
    for r in conn.execute(
        "SELECT s.grupo g, e.api_football_id api, s.puntos pts, s.diferencia dg, s.goles_favor gf "
        "FROM standings s JOIN equipos e ON s.equipo_id=e.id WHERE e.api_football_id IS NOT NULL"
    ):
        base[r["api"]] = [r["pts"], r["dg"], r["gf"]]
        grupos[r["g"]].append(r["api"])
    restantes = []
    for r in conn.execute(
        "SELECT p.grupo g, el.api_football_id h, ev.api_football_id a, el.fifa_code fh "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id "
        "LEFT JOIN resultados rs ON rs.partido_id=p.id WHERE p.grupo IS NOT NULL AND rs.partido_id IS NULL"
    ):
        ventaja = fuerzas["gamma"] if (fuerzas and r["fh"] in HOSTS) else 0.0
        m = _matriz(eq[r["h"]], eq[r["a"]], fuerzas, par_elo, ventaja)
        cum, n = _prep(m)
        restantes.append((r["g"], r["h"], r["a"], cum, n))
    return eq, base, grupos, restantes, fuerzas, par_elo


def simular(estado, n_iter: int, semilla: int = 0):
    eq, base, grupos, restantes, fuerzas, par_elo = estado
    cache = CacheEliminatoria(eq, fuerzas, par_elo)
    rng = np.random.default_rng(semilla)
    avanza, gana_grupo, finalista, campeon = (defaultdict(int) for _ in range(4))
    orden_grupos = sorted(grupos)

    for _ in range(n_iter):
        pts = {a: list(base[a]) for a in base}
        for _g, h, a, cum, n in restantes:
            gi, gj = _sample(cum, n, rng.random())
            ph, pa = pts[h], pts[a]
            ph[1] += gi - gj
            pa[1] += gj - gi
            ph[2] += gi
            pa[2] += gj
            if gi > gj:
                ph[0] += 3
            elif gi < gj:
                pa[0] += 3
            else:
                ph[0] += 1
                pa[0] += 1

        primeros, segundos, terceros = [], [], []
        for g in orden_grupos:
            tabla = sorted(grupos[g], key=lambda a: (pts[a][0], pts[a][1], pts[a][2], rng.random()), reverse=True)
            gana_grupo[tabla[0]] += 1
            avanza[tabla[0]] += 1
            avanza[tabla[1]] += 1
            primeros.append(tabla[0])
            segundos.append(tabla[1])
            terceros.append(tabla[2])
        mejores = sorted(terceros, key=lambda a: (pts[a][0], pts[a][1], pts[a][2], rng.random()), reverse=True)[:8]
        for a in mejores:
            avanza[a] += 1

        ronda = [int(x) for x in rng.permutation(primeros + segundos + mejores)]
        while len(ronda) > 1:
            if len(ronda) == 2:
                for f in ronda:
                    finalista[f] += 1
            ronda = [cache.ganador(ronda[k], ronda[k + 1], rng) for k in range(0, len(ronda), 2)]
        campeon[ronda[0]] += 1

    return {"avanza": avanza, "gana_grupo": gana_grupo, "finalista": finalista, "campeon": campeon}
