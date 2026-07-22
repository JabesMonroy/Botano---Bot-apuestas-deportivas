from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.modelo.liquidacion import MERCADOS_AUTOMATICOS, resultado_mercado
from src.modelo.valor import ev, kelly, sin_vig
from src.reporte import analizar_1x2


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _partido(conn: sqlite3.Connection, local: str, visita: str):
    return conn.execute(
        "SELECT p.id, el.fifa_code fl, ev.fifa_code fv FROM partidos p "
        "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id "
        "WHERE el.fifa_code=? AND ev.fifa_code=?",
        (local, visita),
    ).fetchone()


def partido_id(conn: sqlite3.Connection, local: str, visita: str) -> int | None:
    p = _partido(conn, local, visita)
    return p["id"] if p else None


def registrar_directo(
    conn: sqlite3.Connection, partido: int, mercado: str, seleccion: str,
    cuota_betano: float, prob_modelo: float, stake: float | None = None,
) -> dict:
    evv = ev(prob_modelo, cuota_betano)
    fk = kelly(prob_modelo, cuota_betano)
    st = stake if stake is not None else round(fk * 100, 2)
    with conn:
        conn.execute(
            "INSERT INTO apuestas (partido_id, mercado, seleccion, cuota_betano, stake, prob_modelo, ev, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (partido, mercado, seleccion, cuota_betano, st, prob_modelo, evv, _ahora()),
        )
    return {"ev": evv, "kelly_pct": round(fk * 100, 2), "stake": st}


def registrar_combinada(conn: sqlite3.Connection, patas: list[dict], cuota_total: float, stake: float) -> int:
    fecha = _ahora()
    with conn:
        cur = conn.execute(
            "INSERT INTO combinadas (cuota_total, stake, fecha) VALUES (?, ?, ?)", (cuota_total, stake, fecha)
        )
        combinada_id = cur.lastrowid
        for p in patas:
            conn.execute(
                "INSERT INTO apuestas (partido_id, mercado, seleccion, cuota_betano, prob_modelo, fecha, combinada_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (p["partido_id"], p["mercado"], p["seleccion"], p["cuota_betano"], p["prob_modelo"], fecha, combinada_id),
            )
    return combinada_id


def pendientes(conn: sqlite3.Connection) -> list[dict]:
    filas = conn.execute(
        "SELECT a.id, a.mercado, a.seleccion, a.cuota_betano, a.stake, a.ev, a.fecha, "
        "el.nombre nl, ev2.nombre nv FROM apuestas a JOIN partidos p ON a.partido_id=p.id "
        "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev2 ON p.equipo_visita_id=ev2.id "
        "WHERE a.resultado IS NULL AND a.combinada_id IS NULL ORDER BY a.fecha DESC"
    ).fetchall()
    return [dict(f) for f in filas]


def historial(conn: sqlite3.Connection) -> list[dict]:
    filas = conn.execute(
        "SELECT a.id, a.mercado, a.seleccion, a.cuota_betano, a.cuota_cierre, a.stake, a.prob_modelo, "
        "a.ev, a.clv, a.resultado, a.ganancia, a.fecha, el.nombre nl, ev2.nombre nv FROM apuestas a "
        "JOIN partidos p ON a.partido_id=p.id JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev2 ON p.equipo_visita_id=ev2.id "
        "WHERE a.combinada_id IS NULL ORDER BY a.fecha DESC"
    ).fetchall()
    return [dict(f) for f in filas]


def historial_combinadas(conn: sqlite3.Connection) -> list[dict]:
    combis = conn.execute("SELECT * FROM combinadas ORDER BY fecha DESC").fetchall()
    if not combis:
        return []
    patas_por_combinada: dict[int, list[dict]] = {c["id"]: [] for c in combis}
    for p in conn.execute(
        "SELECT a.id, a.combinada_id, a.mercado, a.seleccion, a.prob_modelo, a.cuota_betano, a.resultado, "
        "el.nombre nl, ev2.nombre nv FROM apuestas a JOIN partidos p ON a.partido_id=p.id "
        "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev2 ON p.equipo_visita_id=ev2.id "
        "WHERE a.combinada_id IN (SELECT id FROM combinadas)"
    ):
        patas_por_combinada.setdefault(p["combinada_id"], []).append(dict(p))
    return [{**dict(c), "patas": patas_por_combinada[c["id"]]} for c in combis]


def marcar_resultado(conn: sqlite3.Connection, apuesta_id: int, gano: bool) -> None:
    fila = conn.execute("SELECT stake, cuota_betano, combinada_id FROM apuestas WHERE id=?", (apuesta_id,)).fetchone()
    resultado = "ganada" if gano else "perdida"
    ganancia = None
    if fila["combinada_id"] is None and fila["stake"] is not None and fila["cuota_betano"] is not None:
        ganancia = round(fila["stake"] * (fila["cuota_betano"] - 1.0) if gano else -fila["stake"], 2)
    with conn:
        conn.execute("UPDATE apuestas SET resultado=?, ganancia=? WHERE id=?", (resultado, ganancia, apuesta_id))
    if fila["combinada_id"] is not None:
        _actualizar_combinadas(conn)


def editar(conn: sqlite3.Connection, apuesta_id: int, cuota_betano: float, stake: float | None) -> None:
    fila = conn.execute("SELECT prob_modelo, resultado, combinada_id FROM apuestas WHERE id=?", (apuesta_id,)).fetchone()
    evv = ev(fila["prob_modelo"], cuota_betano) if fila["prob_modelo"] is not None else None
    ganancia = None
    if fila["resultado"] is not None and fila["combinada_id"] is None and stake is not None:
        ganancia = round(stake * (cuota_betano - 1.0) if fila["resultado"] == "ganada" else -stake, 2)
    with conn:
        conn.execute(
            "UPDATE apuestas SET cuota_betano=?, stake=?, ev=?, ganancia=? WHERE id=?",
            (cuota_betano, stake, evv, ganancia, apuesta_id),
        )


def editar_combinada(conn: sqlite3.Connection, combinada_id: int, cuota_total: float, stake: float) -> None:
    fila = conn.execute("SELECT resultado FROM combinadas WHERE id=?", (combinada_id,)).fetchone()
    ganancia = None
    if fila["resultado"] == "ganada":
        ganancia = round(stake * (cuota_total - 1.0), 2)
    elif fila["resultado"] == "perdida":
        ganancia = -stake
    with conn:
        conn.execute("UPDATE combinadas SET cuota_total=?, stake=?, ganancia=? WHERE id=?", (cuota_total, stake, ganancia, combinada_id))


def eliminar(conn: sqlite3.Connection, apuesta_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM apuestas WHERE id=?", (apuesta_id,))


def eliminar_combinada(conn: sqlite3.Connection, combinada_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM apuestas WHERE combinada_id=?", (combinada_id,))
        conn.execute("DELETE FROM combinadas WHERE id=?", (combinada_id,))


def resumen_dict(conn: sqlite3.Connection) -> dict:
    filas = conn.execute("SELECT clv, ganancia, stake, resultado FROM apuestas WHERE combinada_id IS NULL").fetchall()
    combis = conn.execute("SELECT ganancia, stake, resultado FROM combinadas").fetchall()
    clvs = [f["clv"] for f in filas if f["clv"] is not None]
    liquidadas = [f["ganancia"] for f in filas if f["ganancia"] is not None] + [c["ganancia"] for c in combis if c["ganancia"] is not None]
    stakes_liquidadas = [f["stake"] for f in filas if f["ganancia"] is not None] + [c["stake"] for c in combis if c["ganancia"] is not None]
    n_pendientes = sum(1 for f in filas if f["resultado"] is None) + sum(1 for c in combis if c["resultado"] is None)
    return {
        "n_total": len(filas) + len(combis),
        "n_pendientes": n_pendientes,
        "clv_medio": sum(clvs) / len(clvs) if clvs else None,
        "clv_positivo_pct": (sum(1 for c in clvs if c > 0) / len(clvs)) if clvs else None,
        "n_liquidadas": len(liquidadas),
        "ganancia_total": sum(liquidadas) if liquidadas else None,
        "roi": (sum(liquidadas) / sum(stakes_liquidadas) * 100) if liquidadas else None,
    }


def analiticas(conn: sqlite3.Connection) -> dict:
    filas = conn.execute("SELECT mercado, ev, resultado, ganancia, stake, fecha FROM apuestas WHERE combinada_id IS NULL").fetchall()
    combis = conn.execute("SELECT resultado, ganancia, stake, fecha FROM combinadas").fetchall()

    liquidadas = [dict(f) for f in filas if f["resultado"] is not None] + [dict(c) for c in combis if c["resultado"] is not None]
    n_ganadas = sum(1 for f in liquidadas if f["resultado"] == "ganada")
    tasa_acierto = n_ganadas / len(liquidadas) if liquidadas else None

    evs = [f["ev"] for f in filas if f["ev"] is not None]
    ev_medio = sum(evs) / len(evs) if evs else None

    por_mercado: dict[str, dict] = {}
    for f in filas:
        m = f["mercado"] or "—"
        d = por_mercado.setdefault(m, {"n": 0, "n_ganadas": 0, "n_liquidadas": 0, "ganancia": 0.0, "stake": 0.0})
        d["n"] += 1
        if f["resultado"] is not None:
            d["n_liquidadas"] += 1
            if f["resultado"] == "ganada":
                d["n_ganadas"] += 1
        if f["ganancia"] is not None:
            d["ganancia"] += f["ganancia"]
            d["stake"] += f["stake"] or 0.0
    tabla_mercado = [
        {
            "mercado": m, "n": d["n"],
            "acierto": (d["n_ganadas"] / d["n_liquidadas"] * 100) if d["n_liquidadas"] else None,
            "ganancia": d["ganancia"] if d["n_liquidadas"] else None,
            "roi": (d["ganancia"] / d["stake"] * 100) if d["stake"] else None,
        }
        for m, d in sorted(por_mercado.items(), key=lambda kv: -kv[1]["n"])
    ]

    eventos = sorted(liquidadas, key=lambda e: e["fecha"] or "")
    acumulado = 0.0
    serie = []
    for e in eventos:
        acumulado += e["ganancia"]
        serie.append({"fecha": (e["fecha"] or "")[:10], "banca_acumulada": round(acumulado, 2)})

    resumen_combinadas = None
    if combis:
        c_liquidadas = [c for c in combis if c["resultado"] is not None]
        c_ganadas = sum(1 for c in c_liquidadas if c["resultado"] == "ganada")
        ganancia_c = sum(c["ganancia"] for c in c_liquidadas)
        stake_c = sum(c["stake"] for c in c_liquidadas)
        resumen_combinadas = {
            "n": len(combis),
            "acierto": (c_ganadas / len(c_liquidadas) * 100) if c_liquidadas else None,
            "ganancia": ganancia_c if c_liquidadas else None,
            "roi": (ganancia_c / stake_c * 100) if stake_c else None,
        }

    return {
        "tasa_acierto": tasa_acierto,
        "n_liquidadas": len(liquidadas),
        "ev_medio": ev_medio,
        "por_mercado": tabla_mercado,
        "resumen_combinadas": resumen_combinadas,
        "serie_banca": serie,
    }


def registrar(conn, data_dir: Path, local: str, visita: str, seleccion: str, cuota_betano: float, stake: float | None) -> dict | None:
    if seleccion not in ("1", "X", "2"):
        return None
    a = analizar_1x2(conn, data_dir, local, visita)
    p = _partido(conn, local, visita)
    if a is None or p is None:
        return None
    prob = a.trabajo[seleccion]
    sel_fifa = "X" if seleccion == "X" else (local if seleccion == "1" else visita)
    evv = ev(prob, cuota_betano)
    fk = kelly(prob, cuota_betano)
    st = stake if stake is not None else round(fk * 100, 2)
    with conn:
        conn.execute(
            "INSERT INTO apuestas (partido_id, mercado, seleccion, cuota_betano, stake, prob_modelo, ev, fecha) "
            "VALUES (?, '1X2', ?, ?, ?, ?, ?, ?)",
            (p["id"], sel_fifa, cuota_betano, st, prob, evv, _ahora()),
        )
    return {"seleccion": sel_fifa, "prob": prob, "ev": evv, "kelly_pct": round(fk * 100, 2), "stake": st, "fiable": a.fiable}


def _actualizar_combinadas(conn: sqlite3.Connection) -> int:
    n = 0
    combis = conn.execute("SELECT id, cuota_total, stake FROM combinadas WHERE resultado IS NULL").fetchall()
    with conn:
        for c in combis:
            patas = conn.execute("SELECT resultado FROM apuestas WHERE combinada_id=?", (c["id"],)).fetchall()
            if any(p["resultado"] == "perdida" for p in patas):
                resultado, ganancia = "perdida", -c["stake"]
            elif all(p["resultado"] == "ganada" for p in patas):
                resultado, ganancia = "ganada", round(c["stake"] * (c["cuota_total"] - 1.0), 2)
            else:
                continue
            conn.execute("UPDATE combinadas SET resultado=?, ganancia=? WHERE id=?", (resultado, ganancia, c["id"]))
            n += 1
    return n


def actualizar(conn: sqlite3.Connection) -> int:
    filas = conn.execute(
        "SELECT id, partido_id, mercado, seleccion, cuota_betano, cuota_cierre, clv, stake, combinada_id FROM apuestas "
        "WHERE (cuota_cierre IS NULL AND mercado='1X2') OR resultado IS NULL"
    ).fetchall()
    n = 0
    with conn:
        for f in filas:
            cierre, clv = f["cuota_cierre"], f["clv"]
            if cierre is None and f["mercado"] == "1X2":
                cuotas = {
                    r["seleccion"]: r["cuota"]
                    for r in conn.execute(
                        "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'",
                        (f["partido_id"],),
                    )
                }
                if len(cuotas) == 3 and f["seleccion"] in cuotas:
                    cierre = cuotas[f["seleccion"]]
                    clv = round(f["cuota_betano"] * sin_vig(cuotas)[f["seleccion"]] - 1.0, 4)

            resultado = ganancia = None
            if f["mercado"] in MERCADOS_AUTOMATICOS:
                res = conn.execute(
                    "SELECT goles_local gl, goles_visita gv FROM resultados WHERE partido_id=?", (f["partido_id"],)
                ).fetchone()
                if res is not None and res["gl"] is not None and res["gv"] is not None:
                    gano = resultado_mercado(f["mercado"], f["seleccion"], res["gl"], res["gv"])
                    if gano is not None:
                        resultado = "ganada" if gano else "perdida"
                        if f["combinada_id"] is None and f["stake"] is not None:
                            ganancia = round(f["stake"] * (f["cuota_betano"] - 1.0) if gano else -f["stake"], 2)

            if cierre == f["cuota_cierre"] and resultado is None:
                continue
            conn.execute(
                "UPDATE apuestas SET cuota_cierre=?, clv=?, resultado=?, ganancia=? WHERE id=?",
                (cierre, clv, resultado, ganancia, f["id"]),
            )
            n += 1
    n += _actualizar_combinadas(conn)
    return n


def resumen(conn: sqlite3.Connection) -> None:
    filas = conn.execute(
        "SELECT a.*, el.fifa_code fl, ev.fifa_code fv FROM apuestas a "
        "JOIN partidos p ON a.partido_id=p.id JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id ORDER BY a.fecha"
    ).fetchall()
    if not filas:
        print("sin apuestas registradas")
        return
    print("partido        sel  cuota  cierre   CLV     EV     stake  resultado")
    clvs, ganancias, stakes = [], [], []
    for f in filas:
        clv = f"{f['clv'] * 100:+5.1f}%" if f["clv"] is not None else "  -  "
        cierre = f"{f['cuota_cierre']:.2f}" if f["cuota_cierre"] else " - "
        res = f["resultado"] or "pendiente"
        evtxt = f"{f['ev']:+.3f}" if f["ev"] is not None else "  -   "
        staketxt = f"{f['stake']:5.1f}" if f["stake"] is not None else " combi"
        print(f"  {f['fl']}-{f['fv']:<6} {f['seleccion']:3}  {f['cuota_betano']:.2f}   {cierre}   {clv}  {evtxt}  {staketxt}  {res}")
        if f["clv"] is not None:
            clvs.append(f["clv"])
        if f["ganancia"] is not None:
            ganancias.append(f["ganancia"])
            stakes.append(f["stake"])
    if clvs:
        positivos = sum(1 for c in clvs if c > 0)
        print(f"\nCLV medio: {sum(clvs) / len(clvs) * 100:+.2f}% | CLV positivo: {positivos}/{len(clvs)}")
    if ganancias:
        roi = sum(ganancias) / sum(stakes) * 100
        print(f"Liquidadas: {len(ganancias)} | P/L: {sum(ganancias):+.2f} | ROI: {roi:+.1f}%")
