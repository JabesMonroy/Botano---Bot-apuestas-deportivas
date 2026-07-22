from __future__ import annotations

import json
from datetime import datetime

from src.config import load_config
from src.db.database import connect
from src.ligas import LIGAS
from src.modelo.clubes import ajustar, construir_dataset


def _filas_liga(conn, liga_id: int) -> list[dict]:
    filas = [
        {"fecha": r["fecha"], "local": r["local"], "visita": r["visita"],
         "goles_local": r["goles_local"], "goles_visita": r["goles_visita"],
         "xg_local": r["xg_local"], "xg_visita": r["xg_visita"]}
        for r in conn.execute(
            "SELECT fecha, local, visita, goles_local, goles_visita, xg_local, xg_visita "
            "FROM partidos_club WHERE liga_id=? AND goles_local IS NOT NULL",
            (liga_id,),
        )
    ]
    en_vivo = conn.execute(
        "SELECT p.fecha fecha, COALESCE(el.fd_uk_nombre, el.nombre) local, COALESCE(ev.fd_uk_nombre, ev.nombre) visita, "
        "r.goles_local goles_local, r.goles_visita goles_visita "
        "FROM resultados r JOIN partidos p ON r.partido_id=p.id "
        "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id "
        "WHERE p.liga_id=?",
        (liga_id,),
    ).fetchall()
    for r in en_vivo:
        filas.append({"fecha": r["fecha"][:10], "local": r["local"], "visita": r["visita"],
                      "goles_local": r["goles_local"], "goles_visita": r["goles_visita"],
                      "xg_local": None, "xg_visita": None})
    return filas


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    ref = datetime.now()
    salida = {}
    for liga in LIGAS:
        fila_liga = conn.execute("SELECT id FROM ligas WHERE codigo=?", (liga.codigo,)).fetchone()
        if fila_liga is None:
            continue
        filas = _filas_liga(conn, fila_liga["id"])
        if len(filas) < 380:
            print(f"{liga.nombre}: {len(filas)} partidos, insuficiente para ajustar (mínimo 380)")
            continue
        usar_xg = liga.understat is not None
        params = ajustar(*construir_dataset(filas, ref, usar_xg=usar_xg))
        ruta = cfg.data_dir / "modelos" / f"fuerzas_club_{liga.codigo}.json"
        ruta.write_text(json.dumps(
            {"mu": params["mu"], "gamma": params["gamma"], "rho": params["rho"], "equipos": params["equipos"],
             "n_partidos": len(filas), "usar_xg": usar_xg, "actualizado": ref.isoformat(timespec="seconds")},
            ensure_ascii=False, indent=2,
        ), encoding="utf-8")
        print(f"{liga.nombre}: {len(filas)} partidos | mu={params['mu']:.3f} gamma={params['gamma']:.3f} rho={params['rho']:.2f} | guardado en {ruta.name}")
        salida[liga.codigo] = len(filas)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
