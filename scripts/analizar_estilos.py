from __future__ import annotations

import json
from datetime import datetime, timezone

from src.config import load_config
from src.db.database import connect
from src.modelo.estilos import etiquetas, guardar, medias_torneo, perfiles_wc


def _vivos(conn) -> set[str]:
    filas = conn.execute(
        "SELECT el.fifa_code a, ev.fifa_code b FROM partidos p "
        "JOIN equipos el ON el.id=p.equipo_local_id JOIN equipos ev ON ev.id=p.equipo_visita_id "
        "WHERE p.estado IN ('TIMED','SCHEDULED')"
    ).fetchall()
    return {c for f in filas for c in (f["a"], f["b"])}


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)

    perfiles = perfiles_wc(conn)
    if not perfiles:
        print("sin datos en estadisticas_mundial (corre scripts.ingestar_eventos)")
        return 1
    medias = medias_torneo(perfiles)

    ruta_noticias = cfg.data_dir / "referencia" / "estilos_noticias.json"
    noticias = json.loads(ruta_noticias.read_text(encoding="utf-8")) if ruta_noticias.exists() else {}
    notas = noticias.get("equipos", {})

    salida = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "noticias_fecha": noticias.get("actualizado"),
        "medias_torneo": medias,
        "equipos": {},
    }
    with conn:
        for code, p in perfiles.items():
            et = etiquetas(p, medias)
            salida["equipos"][code] = {
                "nombre": p["nombre"],
                "pj": p["pj"],
                "stats": {k: round(v, 3) for k, v in p.items() if k not in ("fifa_code", "nombre", "pj")},
                "etiquetas": et,
                "nota": notas.get(code, {}).get("nota"),
                "fuentes": notas.get(code, {}).get("fuentes", []),
            }
            conn.execute("UPDATE equipos SET estilo=?, actualizado=? WHERE fifa_code=?",
                         (", ".join(et), salida["actualizado"], code))

    ruta = guardar(cfg.data_dir, salida)
    vivos = _vivos(conn)
    conn.close()

    print(f"estilos calculados para {len(perfiles)} equipos -> {ruta}")
    print(f"medias torneo: xG {medias['xg']:.2f} | tiros {medias['tiros']:.1f} | saques {medias['saques']:.1f} | xG/tiro {medias['xg_por_tiro']:.3f}")
    for code in sorted(vivos):
        e = salida["equipos"].get(code)
        if not e:
            continue
        s = e["stats"]
        print(f"\n{code} ({e['nombre']}, {e['pj']} PJ)")
        print(f"  xG {s['xg_favor']:.2f}/{s['xg_contra']:.2f} | tiros {s['tiros_favor']:.1f}/{s['tiros_contra']:.1f} | "
              f"corners {s['corners_favor']:.1f}/{s['corners_contra']:.1f} | tarjetas {s['tarjetas']:.1f} | "
              f"saques {s['saques_favor']:.1f}/{s['saques_contra']:.1f} | xG/tiro {s['xg_por_tiro']:.3f}")
        print(f"  estilo: {', '.join(e['etiquetas'])}")
        if e["nota"]:
            print(f"  prensa: {e['nota']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
