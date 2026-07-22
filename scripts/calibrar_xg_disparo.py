from __future__ import annotations

import numpy as np

from src.config import load_config
from src.modelo.xg import ajustar_logistico, desde_statsbomb, guardar, prob_gol
from src.statsbomb import BASE, _get_json


def main(comp: int = 43, season: int = 106) -> int:
    cfg = load_config()
    cache = cfg.cache_dir / "statsbomb"
    cache.mkdir(parents=True, exist_ok=True)
    matches = _get_json(f"{BASE}/matches/{comp}/{season}.json", cache / f"matches_{comp}_{season}.json")

    dist, ang, cabeza, gol, xg_sb = [], [], [], [], []
    usados = 0
    for m in matches:
        try:
            eventos = _get_json(f"{BASE}/events/{m['match_id']}.json", cache / f"events_{m['match_id']}.json")
        except Exception:
            continue
        usados += 1
        for e in eventos:
            if e.get("type", {}).get("name") != "Shot":
                continue
            s = e["shot"]
            if s.get("type", {}).get("name") == "Penalty" or not e.get("location"):
                continue
            d, a = desde_statsbomb(e["location"][0], e["location"][1])
            dist.append(d)
            ang.append(a)
            cabeza.append(1.0 if s.get("body_part", {}).get("name") == "Head" else 0.0)
            gol.append(1.0 if s.get("outcome", {}).get("name") == "Goal" else 0.0)
            xg_sb.append(s.get("statsbomb_xg", 0.0))

    if len(dist) < 200:
        print(f"tiros insuficientes ({len(dist)}) para calibrar")
        return 1

    coefs = ajustar_logistico(dist, ang, cabeza, gol)
    pred = np.array([prob_gol(coefs, d, a, c > 0) for d, a, c in zip(dist, ang, cabeza)])
    corr = float(np.corrcoef(pred, np.array(xg_sb))[0, 1])
    meta = {
        "n_tiros": len(dist),
        "n_partidos": usados,
        "conversion_real": round(float(np.mean(gol)), 4),
        "xg_medio_modelo": round(float(np.mean(pred)), 4),
        "corr_vs_statsbomb": round(corr, 4),
        "fuente": "StatsBomb Open Data · FIFA World Cup 2022 (sin penales)",
    }
    guardar(cfg.data_dir, coefs, meta)

    print(f"tiros {len(dist)} de {usados} partidos | conversion real {meta['conversion_real']:.3f} vs xG medio {meta['xg_medio_modelo']:.3f}")
    print(f"correlacion por tiro vs xG de StatsBomb: {corr:.3f}")
    print(f"coeficientes: {[round(c, 4) for c in coefs]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
