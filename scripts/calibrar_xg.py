from __future__ import annotations

import json

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

    xg = {
        r["api_football_id"]: (r["xg_fs"] or 0.0) - (r["xga_fs"] or 0.0)
        for r in conn.execute("SELECT api_football_id, xg_fs, xga_fs FROM equipos WHERE xg_fs IS NOT NULL")
    }
    base_xg = sum(xg.values()) / len(xg)
    for api in fz["fuerzas"]:
        fz["fuerzas"][api]["sx"] = xg.get(int(api), base_xg) - base_xg

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

    def metrica(txg, fn):
        fz["theta_xg"] = txg
        vals = []
        for h, a, vent, nv in datos:
            p = prob_fuerzas(h, a, fz, vent)
            vals.append(fn(p, nv))
        return media(vals)

    def _mae(p, nv):
        return (abs(p[0] - nv["1"]) + abs(p[1] - nv["X"]) + abs(p[2] - nv["2"])) / 3

    def _ce(p, nv):
        import math
        return -(nv["1"] * math.log(max(p[0], 1e-9)) + nv["X"] * math.log(max(p[1], 1e-9)) + nv["2"] * math.log(max(p[2], 1e-9)))

    mae0, ce0 = metrica(0.0, _mae), metrica(0.0, _ce)
    mejor_txg, mejor_ce = 0.0, ce0
    for txg in np.arange(0.0, 0.81, 0.02):
        c = metrica(float(txg), _ce)
        if c < mejor_ce:
            mejor_ce, mejor_txg = c, float(txg)

    fz["theta_xg"] = mejor_txg
    (cfg.data_dir / "modelos" / ARCHIVO).write_text(json.dumps(fz, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"partidos con cuota: {len(datos)}")
    print(f"theta_xg optimo: {mejor_txg:.3f}")
    print(f"cross-entropy vs Pinnacle: {ce0:.4f} (sin xG) -> {mejor_ce:.4f}")
    print(f"MAE vs Pinnacle: {mae0 * 100:.1f}pp (sin xG) -> {metrica(mejor_txg, _mae) * 100:.1f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
