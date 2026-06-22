from __future__ import annotations

import sys
import unicodedata

from src.config import load_config
from src.db.database import connect
from src.modelo.dixon_coles import Ajustes
from src.reporte import analizar_1x2
from src.scrapers.transfermarkt import Transfermarkt

K = 0.6


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def _clasif(pos: str) -> str:
    if any(d in pos for d in ("Goalkeeper", "Back", "Defensive Midfield")):
        return "def"
    if any(o in pos for o in ("Winger", "Forward", "Striker", "Attacking Midfield")):
        return "of"
    return "mix"


def _mults(cfg, tm_id, valor_total, fuera) -> tuple[float, float]:
    if not fuera or not tm_id or not valor_total:
        return 1.0, 1.0
    objetivo = [_norm(x) for x in fuera if x]
    ofensivo = defensivo = 0.0
    for n, pos, v in Transfermarkt(cfg.cache_dir).kader(tm_id):
        if not v or not any(o == _norm(n).split()[-1] or o in _norm(n) for o in objetivo):
            continue
        c = _clasif(pos)
        if c == "of":
            ofensivo += v
        elif c == "def":
            defensivo += v
        else:
            ofensivo += v / 2
            defensivo += v / 2
    mult_ataque = max(1.0 - K * (ofensivo / valor_total), 0.4)
    mult_defensa = min(1.0 + K * (defensivo / valor_total), 1.6)
    return mult_ataque, mult_defensa


def _fila(a, local, visita):
    clave = {"1": local, "X": "Empate", "2": visita}
    return "  ".join(f"{clave[s]} {a.modelo[s] * 100:.1f}%" for s in ("1", "X", "2"))


def main(local: str, visita: str, fuera_local: list[str], fuera_visita: list[str]) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    info = {
        r["fifa_code"]: r
        for r in conn.execute("SELECT fifa_code, transfermarkt_id, valor_plantilla FROM equipos WHERE fifa_code IN (?, ?)", (local, visita))
    }
    if local not in info or visita not in info:
        print("fifa_code no encontrado")
        conn.close()
        return 1

    la_atk, la_def = _mults(cfg, info[local]["transfermarkt_id"], info[local]["valor_plantilla"], fuera_local)
    lv_atk, lv_def = _mults(cfg, info[visita]["transfermarkt_id"], info[visita]["valor_plantilla"], fuera_visita)

    base = analizar_1x2(conn, cfg.data_dir, local, visita)
    ajustes = Ajustes(ataque_local=la_atk, defensa_local=la_def, ataque_visita=lv_atk, defensa_visita=lv_def)
    ajustado = analizar_1x2(conn, cfg.data_dir, local, visita, ajustes)
    conn.close()
    if base is None or ajustado is None:
        print("no se pudo analizar")
        return 1

    print(f"{base.nombre_local} vs {base.nombre_visita}")
    print(f"ajuste por bajas: {local} ataque x{la_atk:.2f} defensa x{la_def:.2f} | {visita} ataque x{lv_atk:.2f} defensa x{lv_def:.2f}")
    print(f"  sin bajas:  {_fila(base, local, visita)}  | goles esp. {base.lh + base.la:.2f}")
    print(f"  con bajas:  {_fila(ajustado, local, visita)}  | goles esp. {ajustado.lh + ajustado.la:.2f}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        print('uso: python -m scripts.impacto_bajas LOCAL VISITA "fuera_local" "fuera_visita"')
        print('  ej: python -m scripts.impacto_bajas ARG AUT "Messi" ""')
        raise SystemExit(1)
    fl = a[2].split(",") if len(a) > 2 and a[2] else []
    fv = a[3].split(",") if len(a) > 3 and a[3] else []
    raise SystemExit(main(a[0].upper(), a[1].upper(), fl, fv))
