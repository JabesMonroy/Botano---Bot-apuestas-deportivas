from __future__ import annotations

import json
import sys

from src.config import load_config
from src.db.database import connect
from src.reporte import analizar_1x2, contexto_partido, generar_markdown, nivel_confianza


def main(local: str, visita: str) -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    a = analizar_1x2(conn, cfg.data_dir, local, visita)
    ctx = contexto_partido(conn, local, visita)
    conn.close()
    if a is None:
        print("no se pudo analizar (codigo o datos faltantes)")
        return 1

    confianza = nivel_confianza(a)
    md = generar_markdown(a, ctx, confianza)
    fecha = (ctx["fecha"][:10] if ctx and ctx["fecha"] else "sinfecha")
    destino = cfg.data_dir / "partidos"
    destino.mkdir(parents=True, exist_ok=True)
    base = destino / f"{fecha}_{local}_vs_{visita}"
    base.with_suffix(".md").write_text(md, encoding="utf-8")
    snapshot = {
        "local": a.local,
        "visita": a.visita,
        "metodo": a.metodo,
        "lambda": [a.lh, a.la],
        "modelo": a.modelo,
        "novig": a.novig,
        "trabajo": a.trabajo,
        "cuotas": a.cuotas,
        "fiable": a.fiable,
        "divergencia": a.divergencia,
        "over25": a.prob["over25"],
        "btts_si": a.prob["btts_si"],
        "confianza": confianza,
        "fecha": ctx["fecha"] if ctx else None,
        "grupo": ctx["grupo"] if ctx else None,
    }
    base.with_suffix(".json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(md)
    print(f"\n[guardado] {base.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(main((args[0] if args else "ARG").upper(), (args[1] if len(args) > 1 else "AUT").upper()))
