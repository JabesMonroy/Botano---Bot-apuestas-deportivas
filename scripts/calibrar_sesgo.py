from __future__ import annotations

import json

import numpy as np

from src.config import load_config
from src.db.database import connect
from src.modelo.evaluacion import media, prob_fuerzas, resultado, rps
from src.modelo.fuerzas import ARCHIVO
from src.modelo.fuerzas import cargar as cargar_fuerzas
from src.modelo.valor import corregir_empate, sin_vig

HOSTS = {"USA", "MEX", "CAN"}
W_MERCADO_DEFAULT = 0.5


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    fz = cargar_fuerzas(cfg.data_dir)
    if fz is None:
        print("faltan fuerzas (corre estimar_fuerzas)")
        return 1

    jugados = conn.execute(
        "SELECT el.api_football_id h, ev.api_football_id a, el.fifa_code fh, r.goles_local gh, r.goles_visita ga "
        "FROM resultados r JOIN partidos p ON r.partido_id=p.id "
        "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id"
    ).fetchall()
    reg = []
    for r in jugados:
        if r["h"] is None or r["a"] is None:
            continue
        p = prob_fuerzas(r["h"], r["a"], fz, fz["gamma"] if r["fh"] in HOSTS else 0.0)
        if p is not None:
            reg.append((p, resultado(r["gh"], r["ga"])))
    base = media([rps(p, o) for p, o in reg])
    delta_rps, rps_rps = 0.0, base
    for delta in np.arange(-0.02, 0.121, 0.005):
        m = media([rps(corregir_empate(*p, float(delta)), o) for p, o in reg])
        if m < rps_rps:
            rps_rps, delta_rps = m, float(delta)

    proximos = conn.execute(
        "SELECT p.id, el.api_football_id h, ev.api_football_id a, el.fifa_code fl, ev.fifa_code fv "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id"
    ).fetchall()
    sesgos = []
    for r in proximos:
        if r["h"] is None or r["a"] is None:
            continue
        cuotas = {
            c["seleccion"]: c["cuota"]
            for c in conn.execute(
                "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'",
                (r["id"],),
            )
        }
        if not {r["fl"], "X", r["fv"]} <= cuotas.keys():
            continue
        p = prob_fuerzas(r["h"], r["a"], fz, 0.0)
        if p is None:
            continue
        nv = sin_vig({"1": cuotas[r["fl"]], "X": cuotas["X"], "2": cuotas[r["fv"]]})
        sesgos.append(p[1] - nv["X"])
    conn.close()

    delta_empate = round(media(sesgos), 3)
    fz["delta_empate"] = delta_empate
    fz["w_mercado"] = W_MERCADO_DEFAULT
    (cfg.data_dir / "modelos" / ARCHIVO).write_text(json.dumps(fz, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[descartado] delta por RPS de {len(reg)} jugados: {delta_rps:+.3f} (mejora {base - rps_rps:.4f}, ruido de muestra pequena)")
    print(f"[usado] delta por divergencia vs Pinnacle ({len(sesgos)} partidos): {delta_empate:+.3f}")
    print(f"sesgo medio empate vs Pinnacle: {media(sesgos):+.3f} -> {media(sesgos) - delta_empate:+.3f} tras corregir")
    print(f"w_mercado (shrinkage) = {W_MERCADO_DEFAULT} | guardado en {ARCHIVO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
