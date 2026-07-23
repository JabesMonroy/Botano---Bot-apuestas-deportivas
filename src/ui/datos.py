from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import streamlit as st

from src.config import Config
from src.db.database import connect


@st.cache_data(show_spinner=False)
def cargar_ligas(cfg: Config) -> list[dict]:
    conn = connect(cfg.db_path)
    filas = conn.execute("SELECT id, codigo, nombre, emblema_url FROM ligas ORDER BY nombre").fetchall()
    conn.close()
    return [dict(r) for r in filas]


@st.cache_data(show_spinner=False)
def cargar_equipos(cfg: Config, liga_id: int) -> dict[str, str]:
    conn = connect(cfg.db_path)
    filas = conn.execute(
        "SELECT e.fifa_code, e.nombre FROM equipos e "
        "JOIN equipos_competicion ec ON ec.equipo_id=e.id WHERE ec.liga_id=? ORDER BY e.nombre",
        (liga_id,),
    ).fetchall()
    conn.close()
    return {f"{r['nombre']} ({r['fifa_code']})": r["fifa_code"] for r in filas}


@st.cache_data(show_spinner=False)
def info_equipo(cfg: Config, fifa_code: str) -> dict | None:
    conn = connect(cfg.db_path)
    fila = conn.execute("SELECT escudo_url, color_principal FROM equipos WHERE fifa_code=?", (fifa_code,)).fetchone()
    conn.close()
    return dict(fila) if fila else None


@st.cache_data(show_spinner=False)
def equipos_busqueda(cfg: Config) -> list[tuple[str, str, str]]:
    from src.lector import ALIAS, _norm

    conn = connect(cfg.db_path)
    filas = conn.execute("SELECT fifa_code, nombre, odds_api_name, eloratings_name FROM equipos").fetchall()
    conn.close()
    out, disp = [], {}
    for r in filas:
        disp[r["fifa_code"]] = r["nombre"]
        for nm in (r["nombre"], r["odds_api_name"], r["eloratings_name"]):
            if nm and len(nm) >= 4:
                out.append((_norm(nm), r["fifa_code"], r["nombre"]))
    for fifa, aliases in ALIAS.items():
        if fifa in disp:
            for al in aliases:
                out.append((_norm(al), fifa, disp[fifa]))
    return out


DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@st.cache_data(ttl=600, show_spinner=False)
def proximos_partidos(cfg: Config, dias: int = 7, liga_id: int | None = None) -> list[dict]:
    bog = timezone(timedelta(hours=-5))
    conn = connect(cfg.db_path)
    condicion = "p.liga_id IS NULL" if liga_id is None else "p.liga_id=?"
    parametros = () if liga_id is None else (liga_id,)
    filas = conn.execute(
        "SELECT p.fecha, p.fase, el.fifa_code lf, el.nombre ln, ev.fifa_code vf, ev.nombre vn "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id "
        f"WHERE p.estado IN ('TIMED','SCHEDULED') AND {condicion} ORDER BY p.fecha",
        parametros,
    ).fetchall()
    conn.close()
    hoy = datetime.now(bog).date()
    out = []
    for r in filas:
        try:
            dt = datetime.fromisoformat((r["fecha"] or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        loc = dt.astimezone(bog)
        dia = (loc.date() - hoy).days
        if not 0 <= dia <= dias:
            continue
        out.append({"dia": dia, "fecha": loc.strftime("%d/%m"), "hora": loc.strftime("%H:%M"),
                    "dia_semana": DIAS_SEMANA[loc.weekday()], "fase": r["fase"],
                    "lf": r["lf"], "ln": r["ln"], "vf": r["vf"], "vn": r["vn"]})
    return out


@st.cache_data(ttl=600, show_spinner=False)
def proximos_todas_ligas(cfg: Config, dias: int = 5) -> list[dict]:
    bog = timezone(timedelta(hours=-5))
    conn = connect(cfg.db_path)
    filas = conn.execute(
        "SELECT p.fecha, p.fase, el.fifa_code lf, el.nombre ln, ev.fifa_code vf, ev.nombre vn, "
        "l.id liga_id, l.codigo liga_codigo, l.nombre liga_nombre, l.emblema_url liga_emblema "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id JOIN ligas l ON p.liga_id=l.id "
        "WHERE p.estado IN ('TIMED','SCHEDULED') ORDER BY p.fecha"
    ).fetchall()
    conn.close()
    hoy = datetime.now(bog).date()
    out = []
    for r in filas:
        try:
            dt = datetime.fromisoformat((r["fecha"] or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        loc = dt.astimezone(bog)
        dia = (loc.date() - hoy).days
        if not 0 <= dia <= dias:
            continue
        out.append({
            "dia": dia, "fecha": loc.strftime("%d/%m"), "hora": loc.strftime("%H:%M"),
            "dia_semana": DIAS_SEMANA[loc.weekday()], "fase": r["fase"],
            "lf": r["lf"], "ln": r["ln"], "vf": r["vf"], "vn": r["vn"],
            "liga_id": r["liga_id"], "liga_codigo": r["liga_codigo"], "liga_nombre": r["liga_nombre"], "liga_emblema": r["liga_emblema"],
        })
    return out


@st.cache_data(ttl=600, show_spinner=False)
def proximo_por_liga(cfg: Config) -> dict:
    bog = timezone(timedelta(hours=-5))
    conn = connect(cfg.db_path)
    filas = conn.execute(
        "SELECT liga_id, MIN(fecha) fecha, COUNT(*) n FROM partidos "
        "WHERE estado IN ('TIMED','SCHEDULED') GROUP BY liga_id"
    ).fetchall()
    conn.close()
    hoy = datetime.now(bog).date()
    out = {}
    for r in filas:
        try:
            dt = datetime.fromisoformat((r["fecha"] or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        loc = dt.astimezone(bog)
        out[r["liga_id"]] = {"fecha": loc.strftime("%d/%m"), "dias": (loc.date() - hoy).days, "n": r["n"]}
    return out


@st.cache_data(show_spinner=False)
def params_tiros(cfg: Config) -> tuple[float, float]:
    ruta = cfg.data_dir / "modelos" / "tiros.json"
    if ruta.exists():
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return d.get("xg_por_tiro", 0.108), d.get("ratio_al_arco", 0.32)
    return 0.108, 0.32


@st.cache_data(show_spinner=False)
def params_corners(cfg: Config) -> tuple[float, float]:
    ruta = cfg.data_dir / "modelos" / "corners.json"
    if ruta.exists():
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return d.get("intercepto", 0.18), d.get("pendiente", 0.57)
    return 0.18, 0.57


@st.cache_data(show_spinner="Consultando estadísticas del árbitro...")
def tasa_arbitro(cfg: Config, nombre: str) -> dict | None:
    if not nombre:
        return None
    try:
        from src.scrapers.transfermarkt import Transfermarkt
        return Transfermarkt(cfg.cache_dir).arbitro_tarjetas(nombre)
    except Exception:
        return None


def actualizar_datos(cfg: Config) -> dict:
    from scripts.actualizar_ligas import actualizar_todas
    from src.apuestas import actualizar as actualizar_apuestas

    r = {"ligas": actualizar_todas(cfg)}
    conn = connect(cfg.db_path)
    try:
        r["apuestas_liquidadas"] = actualizar_apuestas(conn)
    finally:
        conn.close()
    return r
