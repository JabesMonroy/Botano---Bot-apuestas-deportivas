from __future__ import annotations

import json

from src.config import load_config
from src.statsbomb import calibrar_tiros


def main() -> int:
    cfg = load_config()
    print("Descargando eventos del Mundial 2022 (StatsBomb)... puede tardar un minuto.")
    r = calibrar_tiros(cfg.cache_dir, n_partidos=20)
    if not r:
        print("no se pudieron obtener datos")
        return 1
    (cfg.data_dir / "modelos" / "tiros.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"xG/tiro {r['xg_por_tiro']:.3f} | al arco {r['ratio_al_arco'] * 100:.0f}% | conversión {r['conversion'] * 100:.0f}%")
    print(f"({r['n_tiros']} tiros en {r['n_partidos']} partidos del Mundial 2022) → guardado en data/modelos/tiros.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
