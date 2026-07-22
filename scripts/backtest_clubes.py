from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta

from src.config import load_config
from src.db.database import connect
from src.ligas import POR_CODIGO
from src.modelo.clubes import ajustar, construir_dataset, probabilidades
from src.modelo.evaluacion import media, rps
from src.modelo.valor import sin_vig

VENTANA_DIAS = 28


def _filas(conn, liga: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT pc.* FROM partidos_club pc JOIN ligas l ON pc.liga_id = l.id "
            "WHERE l.codigo = ? AND pc.goles_local IS NOT NULL ORDER BY pc.fecha",
            (liga,),
        )
    ]


def _resultado(f: dict) -> int:
    if f["goles_local"] > f["goles_visita"]:
        return 0
    return 1 if f["goles_local"] == f["goles_visita"] else 2


def _novig3(h, d, a) -> tuple[float, float, float] | None:
    if not (h and d and a):
        return None
    nv = sin_vig({"1": h, "X": d, "2": a})
    return nv["1"], nv["X"], nv["2"]


def _novig2(over, under) -> float | None:
    if not (over and under):
        return None
    return sin_vig({"o": over, "u": under})["o"]


def backtest(conn, liga: str, temporadas_test: list[str], usar_xg: bool) -> dict:
    filas = _filas(conn, liga)
    test = [f for f in filas if f["temporada"] in temporadas_test]
    if not test:
        return {}

    inicio = datetime.fromisoformat(min(f["fecha"] for f in test))
    fin = datetime.fromisoformat(max(f["fecha"] for f in test))

    registros = []
    excluidos = 0
    corte = inicio
    while corte <= fin:
        tope = corte + timedelta(days=VENTANA_DIAS)
        train = [f for f in filas if f["fecha"] < corte.date().isoformat()]
        bloque = [f for f in test if corte.date().isoformat() <= f["fecha"] < tope.date().isoformat()]
        if bloque and len(train) >= 380:
            params = ajustar(*construir_dataset(train, corte, usar_xg=usar_xg))
            for f in bloque:
                pr = probabilidades(params, f["local"], f["visita"])
                if pr is None:
                    excluidos += 1
                    continue
                registros.append((f, pr))
        corte = tope

    n = len(registros)
    if n == 0:
        return {}

    hw = sum(1 for f in filas if _resultado(f) == 0) / len(filas)
    dr = sum(1 for f in filas if _resultado(f) == 1) / len(filas)
    base = (hw, dr, 1 - hw - dr)

    rps_modelo = media([rps((p["1"], p["X"], p["2"]), _resultado(f)) for f, p in registros])
    rps_base = media([rps(base, _resultado(f)) for f, _ in registros])

    con_cierre = [(f, p, _novig3(f["psc_h"], f["psc_d"], f["psc_a"])) for f, p in registros]
    con_cierre = [(f, p, nv) for f, p, nv in con_cierre if nv]
    rps_cierre = media([rps(nv, _resultado(f)) for f, _, nv in con_cierre])
    rps_modelo_cc = media([rps((p["1"], p["X"], p["2"]), _resultado(f)) for f, p, _ in con_cierre])

    con_apertura = [(f, p, _novig3(f["ps_h"], f["ps_d"], f["ps_a"])) for f, p in registros]
    con_apertura = [(f, p, nv) for f, p, nv in con_apertura if nv]
    rps_apertura = media([rps(nv, _resultado(f)) for f, _, nv in con_apertura])

    reg_ou = [
        (p["over25"], _novig2(f["pc_over25"], f["pc_under25"]), 1 if f["goles_local"] + f["goles_visita"] > 2.5 else 0)
        for f, p in registros
    ]
    reg_ou = [(pm, pc, y) for pm, pc, y in reg_ou if pc is not None]
    brier_ou_modelo = media([(pm - y) ** 2 for pm, _, y in reg_ou])
    brier_ou_cierre = media([(pc - y) ** 2 for _, pc, y in reg_ou])
    tasa_over = media([y for _, _, y in reg_ou])
    brier_ou_base = media([(tasa_over - y) ** 2 for _, _, y in reg_ou])

    apuestas = []
    for f, p, nv_ap in con_apertura:
        nv_ci = _novig3(f["psc_h"], f["psc_d"], f["psc_a"])
        if nv_ci is None:
            continue
        cuotas_ap = (f["ps_h"], f["ps_d"], f["ps_a"])
        pm = (p["1"], p["X"], p["2"])
        for i in range(3):
            mezcla = 0.35 * pm[i] + 0.65 * nv_ap[i]
            ev = mezcla * cuotas_ap[i] - 1.0
            if ev > 0.02:
                clv = nv_ci[i] * cuotas_ap[i] - 1.0
                gano = _resultado(f) == i
                apuestas.append((ev, clv, gano, cuotas_ap[i]))

    resumen_ap = {}
    if apuestas:
        resumen_ap = {
            "n": len(apuestas),
            "clv_medio": media([a[1] for a in apuestas]),
            "clv_pos": sum(1 for a in apuestas if a[1] > 0) / len(apuestas),
            "roi_plano": media([(a[3] - 1.0) if a[2] else -1.0 for a in apuestas]),
        }

    return {
        "liga": liga,
        "xg": usar_xg,
        "n": n,
        "excluidos": excluidos,
        "rps_modelo": rps_modelo,
        "rps_base": rps_base,
        "rps_cierre": rps_cierre,
        "rps_modelo_cc": rps_modelo_cc,
        "rps_apertura": rps_apertura,
        "n_cierre": len(con_cierre),
        "brier_ou": (brier_ou_modelo, brier_ou_cierre, brier_ou_base, len(reg_ou)),
        "apuestas": resumen_ap,
    }


def _guardar(cfg, liga: str, r: dict) -> None:
    ruta = cfg.data_dir / "modelos" / f"backtest_club_{liga}.json"
    bm, bc, bb, nou = r["brier_ou"]
    ruta.write_text(json.dumps(
        {
            "liga": liga, "xg": r["xg"], "n": r["n"], "n_cierre": r["n_cierre"],
            "rps_modelo": round(r["rps_modelo"], 4), "rps_base": round(r["rps_base"], 4),
            "rps_cierre": round(r["rps_cierre"], 4), "rps_modelo_cc": round(r["rps_modelo_cc"], 4),
            "brier_ou_modelo": round(bm, 4), "brier_ou_cierre": round(bc, 4), "brier_ou_base": round(bb, 4), "n_ou": nou,
            "apuestas": r["apuestas"],
        },
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")


def main(argv: list[str]) -> int:
    ligas = [a for a in argv if not a.startswith("20")] or ["E0"]
    temporadas = [a for a in argv if a.startswith("20")] or ["2024-25", "2025-26"]
    cfg = load_config()
    conn = connect(cfg.db_path)
    for liga in ligas:
        usar_xg_liga = POR_CODIGO[liga].understat is not None if liga in POR_CODIGO else True
        for usar_xg in (False, True):
            r = backtest(conn, liga, temporadas, usar_xg)
            if not r:
                print(f"{liga}: sin datos de test")
                continue
            et = "0.7xG+0.3goles" if usar_xg else "solo goles"
            print(f"\n=== {liga} | objetivo: {et} | test {'+'.join(temporadas)} (n={r['n']}, excluidos {r['excluidos']}) ===")
            print(f"1X2 RPS  modelo {r['rps_modelo']:.4f} | base liga {r['rps_base']:.4f} | "
                  f"cierre Pinnacle {r['rps_cierre']:.4f} (modelo mismo subconjunto {r['rps_modelo_cc']:.4f}, n={r['n_cierre']}) | "
                  f"apertura {r['rps_apertura']:.4f}")
            bm, bc, bb, nou = r["brier_ou"]
            print(f"O/U 2.5 Brier  modelo {bm:.4f} | cierre {bc:.4f} | base {bb:.4f} (n={nou})")
            if r["apuestas"]:
                a = r["apuestas"]
                print(f"apuestas simuladas (EV>2% vs apertura, mezcla 35/65): n={a['n']} | "
                      f"CLV medio {a['clv_medio']*100:+.2f}% | CLV>0 {a['clv_pos']*100:.0f}% | ROI plano {a['roi_plano']*100:+.2f}%")
            if usar_xg == usar_xg_liga:
                _guardar(cfg, liga, r)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
