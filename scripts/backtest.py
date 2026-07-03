from __future__ import annotations

import json

from src.config import load_config
from src.db.database import connect
from src.modelo.evaluacion import brier, brier_bin, calibracion, calibracion_bin, ece, estrato, media, prob_fuerzas, prob_over, resultado, rps
from src.modelo.fuerzas import _filas_historico, _filas_mundial, _parse, ajustar, cargar as cargar_fuerzas, construir_dataset, mapa_elo

HOSTS = {"USA", "MEX", "CAN"}


def _estratos(registros, base):
    out = []
    for et in ("facil", "medio", "renido"):
        sub = [(p, o) for p, o in registros if estrato(p) == et]
        if sub:
            out.append({
                "estrato": et, "n": len(sub),
                "rps_modelo": round(media([rps(p, o) for p, o in sub]), 4),
                "rps_base": round(media([rps(base, o) for _, o in sub]), 4),
            })
    return out


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)

    filas = [r for r in _filas_historico(conn) if _parse(r["fecha"])]
    filas.sort(key=lambda r: _parse(r["fecha"]))
    corte = int(len(filas) * 0.7)
    train, test = filas[:corte], filas[corte:]
    elo = mapa_elo(conn, cfg.cache_dir)
    ds = construir_dataset(train, elo, min_partidos=5)
    params = ajustar(*ds[:8])

    n = len(train)
    hw = sum(1 for r in train if r["gh"] > r["ga"])
    dr = sum(1 for r in train if r["gh"] == r["ga"])
    ingenuo = (hw / n, dr / n, (n - hw - dr) / n)

    reg = []
    for r in test:
        p = prob_fuerzas(r["h"], r["a"], params, params["gamma"])
        if p is not None:
            reg.append((p, resultado(r["gh"], r["ga"])))

    out = {
        "corte": str(_parse(test[0]["fecha"]).date()),
        "train": len(train), "test": len(test), "evaluables": len(reg),
        "rps_modelo": round(media([rps(p, o) for p, o in reg]), 4),
        "rps_ingenuo": round(media([rps(ingenuo, o) for _, o in reg]), 4),
        "brier": round(brier(reg), 4),
        "ece": round(ece(reg), 4),
        "estratos": _estratos(reg, ingenuo),
        "calibracion": calibracion(reg),
    }
    out["mejora_pct"] = round((out["rps_ingenuo"] - out["rps_modelo"]) / out["rps_ingenuo"] * 100, 1)

    ou_reg = {1.5: [], 2.5: [], 3.5: []}
    for r in test:
        po = prob_over(r["h"], r["a"], params, [1.5, 2.5, 3.5], params["gamma"])
        if po is None:
            continue
        for L in ou_reg:
            ou_reg[L].append((po[L], 1.0 if (r["gh"] + r["ga"]) > L else 0.0))
    ou = {}
    for L, reg_l in ou_reg.items():
        if not reg_l:
            continue
        base = sum(o for _, o in reg_l) / len(reg_l)
        ou[str(L)] = {
            "n": len(reg_l),
            "tasa_over_real": round(base, 4),
            "tasa_over_modelo": round(sum(p for p, _ in reg_l) / len(reg_l), 4),
            "brier_modelo": round(brier_bin(reg_l), 4),
            "brier_base": round(brier_bin([(base, o) for _, o in reg_l]), 4),
            "calibracion": calibracion_bin(reg_l),
        }
        ou[str(L)]["mejora_pct"] = round((ou[str(L)]["brier_base"] - ou[str(L)]["brier_modelo"]) / ou[str(L)]["brier_base"] * 100, 1)
    out["over_under"] = ou

    fz = cargar_fuerzas(cfg.data_dir)
    reg2 = []
    for r in _filas_mundial(conn):
        ventaja = fz["gamma"] if not r["neutral"] else 0.0
        p = prob_fuerzas(r["h"], r["a"], fz, ventaja)
        if p is not None:
            reg2.append((p, resultado(r["gh"], r["ga"])))
    if reg2:
        uni = (1 / 3, 1 / 3, 1 / 3)
        out["mundial"] = {
            "n": len(reg2),
            "rps_modelo": round(media([rps(p, o) for p, o in reg2]), 4),
            "rps_uniforme": round(media([rps(uni, o) for _, o in reg2]), 4),
            "brier": round(brier(reg2), 4),
            "estratos": _estratos(reg2, uni),
            "calibracion": calibracion(reg2, nbins=5),
        }
    conn.close()

    (cfg.data_dir / "modelos" / "backtest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"corte {out['corte']} | test {out['test']} | RPS modelo {out['rps_modelo']} vs ingenuo {out['rps_ingenuo']} ({out['mejora_pct']:+.1f}%)")
    print(f"Brier {out['brier']} | ECE {out['ece']}")
    for e in out["estratos"]:
        print(f"  {e['estrato']:7} n={e['n']:4} RPS {e['rps_modelo']} vs {e['rps_base']} ({'mejor' if e['rps_modelo'] < e['rps_base'] else 'PEOR'})")
    print("Over/Under (Brier modelo vs base = predecir la tasa media):")
    for L, d in out["over_under"].items():
        print(f"  +{L}: Brier {d['brier_modelo']} vs {d['brier_base']} ({d['mejora_pct']:+.1f}%) | real {d['tasa_over_real']} pred {d['tasa_over_modelo']}")
    print("guardado en data/modelos/backtest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
