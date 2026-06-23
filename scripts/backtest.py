from __future__ import annotations

import json

from src.config import load_config
from src.db.database import connect
from src.modelo.evaluacion import brier, calibracion, ece, estrato, media, prob_fuerzas, resultado, rps
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
    params = ajustar(*ds[:7])

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

    fz = cargar_fuerzas(cfg.data_dir)
    reg2 = []
    for r in _filas_mundial(conn):
        ventaja = fz["gamma"] if False else 0.0
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
    print("guardado en data/modelos/backtest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
