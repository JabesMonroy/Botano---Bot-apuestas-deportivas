from __future__ import annotations

import json
import math

import numpy as np

from src.config import load_config
from src.db.database import connect
from src.modelo.evaluacion import media, prob_fuerzas
from src.modelo.fuerzas import ARCHIVO
from src.modelo.fuerzas import cargar as cargar_fuerzas
from src.modelo.valor import sin_vig

HOSTS = {"USA", "MEX", "CAN"}


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    fz = cargar_fuerzas(cfg.data_dir)
    if fz is None:
        print("faltan fuerzas (corre estimar_fuerzas)")
        return 1

    valores = {
        r["api_football_id"]: r["valor_plantilla"]
        for r in conn.execute("SELECT api_football_id, valor_plantilla FROM equipos WHERE valor_plantilla IS NOT NULL")
    }
    logs = {api: math.log(v) for api, v in valores.items() if v}
    base = sum(logs.values()) / len(logs)
    for api in fz["fuerzas"]:
        fz["fuerzas"][api]["w"] = logs.get(int(api), base) - base

    datos = []
    for r in conn.execute(
        "SELECT p.id, el.api_football_id h, ev.api_football_id a, el.fifa_code fl, ev.fifa_code fv "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id"
    ):
        if r["h"] is None or r["a"] is None:
            continue
        cuotas = {
            c["seleccion"]: c["cuota"]
            for c in conn.execute(
                "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'", (r["id"],)
            )
        }
        if not {r["fl"], "X", r["fv"]} <= cuotas.keys():
            continue
        nv = sin_vig({"1": cuotas[r["fl"]], "X": cuotas["X"], "2": cuotas[r["fv"]]})
        vent = fz["gamma"] if r["fl"] in HOSTS else 0.0
        if prob_fuerzas(r["h"], r["a"], fz, vent) is None:
            continue
        datos.append((r["h"], r["a"], vent, nv))
    conn.close()

    def ce(tv: float) -> float:
        fz["theta_valor"] = tv
        tot = 0.0
        for h, a, vent, nv in datos:
            p = prob_fuerzas(h, a, fz, vent)
            tot += -(nv["1"] * math.log(max(p[0], 1e-9)) + nv["X"] * math.log(max(p[1], 1e-9)) + nv["2"] * math.log(max(p[2], 1e-9)))
        return tot / len(datos)

    def mae(tv: float) -> float:
        fz["theta_valor"] = tv
        difs = []
        for h, a, vent, nv in datos:
            p = prob_fuerzas(h, a, fz, vent)
            difs.append((abs(p[0] - nv["1"]) + abs(p[1] - nv["X"]) + abs(p[2] - nv["2"])) / 3)
        return media(difs)

    ce0, mae0 = ce(0.0), mae(0.0)
    mejor_tv, mejor_ce = 0.0, ce0
    for tv in np.arange(0.0, 0.61, 0.02):
        c = ce(float(tv))
        if c < mejor_ce:
            mejor_ce, mejor_tv = c, float(tv)

    fz["theta_valor"] = mejor_tv
    (cfg.data_dir / "modelos" / ARCHIVO).write_text(json.dumps(fz, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"partidos con cuota: {len(datos)}")
    print(f"theta_valor optimo: {mejor_tv:.3f}")
    print(f"cross-entropy vs Pinnacle: {ce0:.4f} (sin valor) -> {mejor_ce:.4f}")
    print(f"MAE vs Pinnacle: {mae0 * 100:.1f}pp (sin valor) -> {mae(mejor_tv) * 100:.1f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
