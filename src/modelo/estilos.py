from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ARCHIVO = "estilos.json"

CONSULTA = """
SELECT e.fifa_code, e.nombre, COUNT(*) pj,
       AVG(em.xg) xg_favor, AVG(riv.xg) xg_contra,
       AVG(em.goles) goles_favor, AVG(riv.goles) goles_contra,
       AVG(em.tiros) tiros_favor, AVG(riv.tiros) tiros_contra,
       AVG(em.corners) corners_favor, AVG(riv.corners) corners_contra,
       AVG(em.amarillas + em.rojas) tarjetas,
       AVG(em.saques_meta) saques_favor, AVG(riv.saques_meta) saques_contra
FROM estadisticas_mundial em
JOIN estadisticas_mundial riv ON riv.partido_id = em.partido_id AND riv.equipo_id != em.equipo_id
JOIN equipos e ON e.id = em.equipo_id
GROUP BY em.equipo_id
"""


def perfiles_wc(conn: sqlite3.Connection) -> dict[str, dict]:
    perfiles: dict[str, dict] = {}
    for r in conn.execute(CONSULTA):
        p = dict(r)
        p["xg_por_tiro"] = p["xg_favor"] / p["tiros_favor"] if p["tiros_favor"] else 0.0
        perfiles[p["fifa_code"]] = p
    return perfiles


def medias_torneo(perfiles: dict[str, dict]) -> dict[str, float]:
    n = len(perfiles)
    if not n:
        return {}
    xg = sum(p["xg_favor"] for p in perfiles.values()) / n
    tiros = sum(p["tiros_favor"] for p in perfiles.values()) / n
    saques = sum(p["saques_favor"] for p in perfiles.values()) / n
    return {"xg": xg, "tiros": tiros, "saques": saques, "xg_por_tiro": xg / tiros if tiros else 0.0}


def etiquetas(p: dict, medias: dict[str, float]) -> list[str]:
    et: list[str] = []
    xg, xga = p["xg_favor"], p["xg_contra"]
    if xg >= 1.9:
        et.append("muy ofensivo")
    elif xg >= 1.5:
        et.append("ofensivo")
    elif xg < 0.95:
        et.append("conservador en ataque")
    if xga <= 0.65:
        et.append("muy sólido atrás")
    elif xga <= 0.9:
        et.append("sólido atrás")
    elif xga >= 1.4:
        et.append("frágil atrás")
    dif_tiros = p["tiros_favor"] - p["tiros_contra"]
    if dif_tiros >= 6 and p["corners_favor"] >= p["corners_contra"]:
        et.append("dominador territorial")
    if dif_tiros <= -2 and p["xg_por_tiro"] >= medias["xg_por_tiro"] * 1.2:
        et.append("contragolpeador")
    if p["saques_favor"] >= medias["saques"] + 1.5:
        et.append("bloque bajo y juego directo")
    if p["saques_contra"] >= medias["saques"] + 1.5:
        et.append("encierra al rival")
    if p["xg_por_tiro"] >= 0.125:
        et.append("ocasiones de alta calidad")
    elif p["xg_por_tiro"] <= 0.09 and p["tiros_favor"] >= medias["tiros"]:
        et.append("mucho tiro de bajo valor")
    if p["goles_favor"] - xg >= 0.5:
        et.append("definición clínica (sobre xG)")
    if p["tarjetas"] >= 1.5:
        et.append("friccionador (tarjetas)")
    elif p["tarjetas"] <= 0.6:
        et.append("disciplinado")
    if xg + xga >= 3.0:
        et.append("partidos abiertos")
    elif xg + xga <= 2.1:
        et.append("partidos cerrados")
    return et or ["equilibrado"]


def cargar(data_dir: Path) -> dict | None:
    ruta = data_dir / "modelos" / ARCHIVO
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar(data_dir: Path, estilos: dict) -> Path:
    ruta = data_dir / "modelos" / ARCHIVO
    ruta.write_text(json.dumps(estilos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta
