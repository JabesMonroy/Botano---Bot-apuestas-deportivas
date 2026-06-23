from __future__ import annotations

import json

from src.config import load_config
from src.statsbomb import calibrar_corners


def main() -> int:
    cfg = load_config()
    print("Descargando eventos del Mundial 2022 (StatsBomb)... puede tardar un minuto.")
    r = calibrar_corners(cfg.cache_dir, n_partidos=40)
    if not r:
        print("no se pudieron obtener datos")
        return 1
    (cfg.data_dir / "modelos" / "corners.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"reparto córners local = {r['intercepto']:.3f} + {r['pendiente']:.3f}·(reparto de dominio) | total medio {r['total_medio']}")
    print(f"({r['n_partidos']} partidos del Mundial 2022) → guardado en data/modelos/corners.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
