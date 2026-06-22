from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.modelo.dixon_coles import Ajustes, ParametrosModelo, lambdas, matriz_marcadores, mercados
from src.modelo.fuerzas import cargar as cargar_fuerzas
from src.modelo.fuerzas import lambdas_desde_fuerzas
from src.modelo.parametros import HOSTS
from src.modelo.parametros import cargar as cargar_par
from src.modelo.valor import corregir_empate, ev, mezclar_1x2, sin_vig

UMBRAL_DIVERGENCIA = 0.18


@dataclass
class Analisis:
    local: str
    visita: str
    nombre_local: str
    nombre_visita: str
    metodo: str
    lh: float
    la: float
    prob: dict
    modelo: dict
    novig: dict
    trabajo: dict
    cuotas: dict
    fiable: bool
    divergencia: float
    matriz: np.ndarray


def analizar_1x2(conn: sqlite3.Connection, data_dir: Path, local: str, visita: str, ajustes: Ajustes | None = None) -> Analisis | None:
    eq = {r["fifa_code"]: r for r in conn.execute("SELECT fifa_code, nombre, elo, api_football_id FROM equipos")}
    if local not in eq or visita not in eq:
        return None

    aj = ajustes or Ajustes()
    fuerzas = cargar_fuerzas(data_dir)
    res = None
    if fuerzas and eq[local]["api_football_id"] and eq[visita]["api_football_id"]:
        ventaja = fuerzas["gamma"] if local in HOSTS else 0.0
        res = lambdas_desde_fuerzas(eq[local]["api_football_id"], eq[visita]["api_football_id"], fuerzas, aj, ventaja_local=ventaja)
    if res is not None:
        lh, la = res
        par = ParametrosModelo(tasa_base=0.0, rho=fuerzas["rho"])
        delta, w_mercado, metodo = fuerzas.get("delta_empate", 0.0), fuerzas.get("w_mercado", 0.5), "fuerzas"
    else:
        if eq[local]["elo"] is None or eq[visita]["elo"] is None:
            return None
        par = cargar_par(data_dir, conn, local_es_host=local in HOSTS)
        lh, la = lambdas(eq[local]["elo"], eq[visita]["elo"], par, aj)
        delta, w_mercado, metodo = 0.0, 0.5, "elo"

    matriz = matriz_marcadores(lh, la, par)
    prob = mercados(matriz)
    p1, px, p2 = corregir_empate(prob["1"], prob["X"], prob["2"], delta)
    modelo = {"1": p1, "X": px, "2": p2}

    partido = conn.execute(
        "SELECT p.id FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id WHERE el.fifa_code=? AND ev.fifa_code=?",
        (local, visita),
    ).fetchone()
    cuotas: dict[str, float] = {}
    if partido:
        for r in conn.execute(
            "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'",
            (partido["id"],),
        ):
            cuotas[r["seleccion"]] = r["cuota"]

    clave = {"1": local, "X": "X", "2": visita}
    novig = sin_vig({s: cuotas[clave[s]] for s in ("1", "X", "2")}) if len(cuotas) >= 3 else {}
    trabajo = mezclar_1x2(modelo, novig, w_mercado) if novig else modelo
    divergencia = max(abs(modelo[s] - novig[s]) for s in ("1", "X", "2")) if novig else 0.0
    fiable = divergencia <= UMBRAL_DIVERGENCIA

    return Analisis(
        local, visita, eq[local]["nombre"], eq[visita]["nombre"], metodo, lh, la,
        prob, modelo, novig, trabajo, cuotas, fiable, divergencia, matriz,
    )


def contexto_partido(conn: sqlite3.Connection, local: str, visita: str) -> dict | None:
    row = conn.execute(
        "SELECT p.fecha, p.fase, p.grupo, p.estado FROM partidos p "
        "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id "
        "WHERE el.fifa_code=? AND ev.fifa_code=?",
        (local, visita),
    ).fetchone()
    if row is None:
        return None
    standings = conn.execute(
        "SELECT s.posicion, e.fifa_code, e.nombre, s.jugados, s.puntos, s.goles_favor, s.goles_contra, s.diferencia "
        "FROM standings s JOIN equipos e ON s.equipo_id=e.id WHERE s.grupo=? ORDER BY s.posicion",
        (row["grupo"],),
    ).fetchall()
    return {"fecha": row["fecha"], "fase": row["fase"], "grupo": row["grupo"], "estado": row["estado"], "standings": standings}


def nivel_confianza(a: Analisis) -> str:
    if not a.novig:
        return "bajo (sin cuota de mercado)"
    if not a.fiable:
        return "bajo (el modelo diverge del mercado sharp)"
    if a.metodo == "elo":
        return "medio (fallback Elo, sin fuerzas estimadas)"
    return "alto" if a.divergencia <= 0.08 else "medio"


def generar_markdown(a: Analisis, ctx: dict | None, confianza: str) -> str:
    clave = {"1": a.local, "X": "X", "2": a.visita}
    etq = {"1": a.nombre_local, "X": "Empate", "2": a.nombre_visita}
    out = [f"# {a.nombre_local} vs {a.nombre_visita}"]

    if ctx:
        fecha = ctx["fecha"][:16].replace("T", " ") if ctx["fecha"] else "?"
        out.append(f"\n**Grupo {ctx['grupo']}** · {ctx['fase']} · {fecha} UTC · estado: {ctx['estado']}")
        out.append("\n## Contexto de grupo\n")
        out.append("| Pos | Equipo | PJ | Pts | GF:GC | DG |")
        out.append("|---|---|---|---|---|---|")
        for s in ctx["standings"]:
            marca = " ◄" if s["fifa_code"] in (a.local, a.visita) else ""
            out.append(f"| {s['posicion']} | {s['nombre']}{marca} | {s['jugados']} | {s['puntos']} | {s['goles_favor']}:{s['goles_contra']} | {s['diferencia']:+d} |")

    out.append("\n## Probabilidades 1X2\n")
    out.append("| Resultado | Modelo | Pinnacle | Trabajo | Cuota | EV |")
    out.append("|---|---|---|---|---|---|")
    for s in ("1", "X", "2"):
        pin = f"{a.novig[s] * 100:.1f}%" if s in a.novig else "—"
        cu = a.cuotas.get(clave[s])
        evv = (f"{ev(a.trabajo[s], cu):+.3f}" if a.fiable else "n/f") if cu else "—"
        out.append(f"| {etq[s]} | {a.modelo[s] * 100:.1f}% | {pin} | {a.trabajo[s] * 100:.1f}% | {cu or '—'} | {evv} |")

    out.append("\n## Goles\n")
    out.append(f"- Goles esperados: **{a.lh + a.la:.2f}** (λ {a.lh:.2f} − {a.la:.2f})")
    out.append(f"- Over 2.5: {a.prob['over25'] * 100:.1f}% · Under 2.5: {a.prob['under25'] * 100:.1f}%")
    out.append(f"- Ambos anotan: Sí {a.prob['btts_si'] * 100:.1f}% · No {a.prob['btts_no'] * 100:.1f}%")

    out.append(f"\n**Confianza del análisis:** {confianza}")
    if a.novig and not a.fiable:
        out.append(f"\n> ⚠ El modelo diverge {a.divergencia * 100:.0f}pp del mercado sharp: EV no válido (probable fallo del modelo, no valor). No apostar por esta discrepancia.")
    out.append("\n*Herramienta de análisis, no recomendación de apuesta. El fútbol tiene varianza irreducible.*")
    return "\n".join(out)
