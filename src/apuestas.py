from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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


def actualizar(conn: sqlite3.Connection) -> int:
    filas = conn.execute(
        "SELECT id, partido_id, seleccion, cuota_betano, stake FROM apuestas WHERE cuota_cierre IS NULL"
    ).fetchall()
    n = 0
    with conn:
        for f in filas:
            cuotas = {
                r["seleccion"]: r["cuota"]
                for r in conn.execute(
                    "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'",
                    (f["partido_id"],),
                )
            }
            if len(cuotas) < 3 or f["seleccion"] not in cuotas:
                continue
            novig = sin_vig(cuotas)
            clv = f["cuota_betano"] * novig[f["seleccion"]] - 1.0
            res = conn.execute(
                "SELECT goles_local gl, goles_visita gv FROM resultados WHERE partido_id=?", (f["partido_id"],)
            ).fetchone()
            resultado = ganancia = None
            if res is not None:
                info = conn.execute(
                    "SELECT el.fifa_code fl, ev.fifa_code fv FROM partidos p "
                    "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id WHERE p.id=?",
                    (f["partido_id"],),
                ).fetchone()
                real = info["fl"] if res["gl"] > res["gv"] else ("X" if res["gl"] == res["gv"] else info["fv"])
                gano = f["seleccion"] == real
                resultado = "ganada" if gano else "perdida"
                ganancia = round(f["stake"] * (f["cuota_betano"] - 1.0) if gano else -f["stake"], 2)
            conn.execute(
                "UPDATE apuestas SET cuota_cierre=?, clv=?, resultado=?, ganancia=? WHERE id=?",
                (cuotas[f["seleccion"]], round(clv, 4), resultado, ganancia, f["id"]),
            )
            n += 1
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
        print(f"  {f['fl']}-{f['fv']:<6} {f['seleccion']:3}  {f['cuota_betano']:.2f}   {cierre}   {clv}  {f['ev']:+.3f}  {f['stake']:5.1f}  {res}")
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
