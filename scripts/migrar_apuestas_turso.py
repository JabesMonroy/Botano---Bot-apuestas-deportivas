from __future__ import annotations

from src.config import load_config
from src.db import turso
from src.db.database import connect


def main() -> int:
    cfg = load_config()
    conn_local = connect(cfg.db_path)
    conn_turso = turso.connect(cfg)

    ya_combis = {r["id"] for r in conn_turso.execute("SELECT id FROM combinadas").fetchall()}
    combis = conn_local.execute("SELECT * FROM combinadas ORDER BY id").fetchall()
    n_combis = 0
    for c in combis:
        if c["id"] in ya_combis:
            continue
        conn_turso.execute(
            "INSERT INTO combinadas (id, cuota_total, stake, fecha, resultado, ganancia) VALUES (?, ?, ?, ?, ?, ?)",
            (c["id"], c["cuota_total"], c["stake"], c["fecha"], c["resultado"], c["ganancia"]),
        )
        n_combis += 1
    conn_turso.commit()

    ya_apuestas = {r["id"] for r in conn_turso.execute("SELECT id FROM apuestas").fetchall()}
    filas = conn_local.execute(
        "SELECT a.*, el.nombre nl, el.fifa_code fl, ev.nombre nv, ev.fifa_code fv FROM apuestas a "
        "LEFT JOIN partidos p ON a.partido_id=p.id LEFT JOIN equipos el ON p.equipo_local_id=el.id "
        "LEFT JOIN equipos ev ON p.equipo_visita_id=ev.id ORDER BY a.id"
    ).fetchall()
    n_apuestas = 0
    for f in filas:
        if f["id"] in ya_apuestas:
            continue
        conn_turso.execute(
            "INSERT INTO apuestas (id, partido_id, equipo_local_nombre, equipo_visita_nombre, equipo_local_fifa, "
            "equipo_visita_fifa, mercado, seleccion, cuota_betano, cuota_cierre, stake, prob_modelo, ev, clv, "
            "resultado, ganancia, fecha, combinada_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f["id"], f["partido_id"], f["nl"], f["nv"], f["fl"], f["fv"], f["mercado"], f["seleccion"],
             f["cuota_betano"], f["cuota_cierre"], f["stake"], f["prob_modelo"], f["ev"], f["clv"],
             f["resultado"], f["ganancia"], f["fecha"], f["combinada_id"]),
        )
        n_apuestas += 1
    conn_turso.commit()

    total_local_ap = len(filas)
    total_turso_ap = conn_turso.execute("SELECT COUNT(*) n FROM apuestas").fetchone()["n"]
    total_local_combis = len(combis)
    total_turso_combis = conn_turso.execute("SELECT COUNT(*) n FROM combinadas").fetchone()["n"]

    conn_local.close()
    conn_turso.close()

    print(f"migradas {n_combis} combinada(s) nueva(s) y {n_apuestas} apuesta(s)/pata(s) nueva(s) a Turso")
    print(f"combinadas: local={total_local_combis} turso={total_turso_combis}")
    print(f"apuestas:   local={total_local_ap} turso={total_turso_ap}")
    if total_local_ap != total_turso_ap or total_local_combis != total_turso_combis:
        print("AVISO: los totales no coinciden, revisar antes de borrar datos locales")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
