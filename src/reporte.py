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
from src.modelo.secundarios import over_under
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
    corners_esp: float | None
    tarjetas_esp: float | None
    perfil_local: dict
    perfil_visita: dict


def analizar_1x2(conn: sqlite3.Connection, data_dir: Path, local: str, visita: str, ajustes: Ajustes | None = None) -> Analisis | None:
    eq = {
        r["fifa_code"]: r
        for r in conn.execute(
            "SELECT fifa_code, nombre, confederacion, elo, api_football_id, valor_plantilla, "
            "xg_fs, xga_fs, corners_favor, tarjetas_partido FROM equipos"
        )
    }
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

    cl, cv = eq[local]["corners_favor"], eq[visita]["corners_favor"]
    tl, tv = eq[local]["tarjetas_partido"], eq[visita]["tarjetas_partido"]
    corners_esp = (cl + cv) / 2 if (cl and cv) else None
    tarjetas_esp = (tl + tv) if (tl and tv) else None

    return Analisis(
        local, visita, eq[local]["nombre"], eq[visita]["nombre"], metodo, lh, la,
        prob, modelo, novig, trabajo, cuotas, fiable, divergencia, matriz, corners_esp, tarjetas_esp,
        dict(eq[local]), dict(eq[visita]),
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


def _val(v, fmt: str = "{:.0f}", suf: str = "") -> str:
    return (fmt.format(v) + suf) if v is not None else "—"


def _xg(p: dict) -> str:
    if p.get("xg_fs") is not None and p.get("xga_fs") is not None:
        return f"{p['xg_fs']:.2f}/{p['xga_fs']:.2f}"
    return "—"


def formato_consola(a: Analisis, ctx: dict | None, confianza: str) -> str:
    anc = 62
    nl, nv = a.nombre_local, a.nombre_visita
    cl, cv = nl[:13], nv[:13]
    pl, pv = a.perfil_local, a.perfil_visita
    out = ["", "=" * anc, f"  {nl.upper()}  vs  {nv.upper()}"]
    if ctx:
        fecha = ctx["fecha"][:16].replace("T", " ") if ctx["fecha"] else "?"
        estado = {"TIMED": "por jugarse", "SCHEDULED": "por jugarse", "FINISHED": "finalizado", "IN_PLAY": "en juego"}.get(ctx["estado"], ctx["estado"])
        out.append(f"  Grupo {ctx['grupo']} · {fecha} · {estado}")
    out.append("=" * anc)

    out.append("")
    out.append(f"  PERFIL                {cl:>13} {cv:>13}")
    out.append(f"  Confederación         {str(pl.get('confederacion') or '—'):>13} {str(pv.get('confederacion') or '—'):>13}")
    out.append(f"  Elo                   {_val(pl.get('elo')):>13} {_val(pv.get('elo')):>13}")
    out.append(f"  Valor plantilla       {_val(pl.get('valor_plantilla'), '{:.0f}', ' M€'):>13} {_val(pv.get('valor_plantilla'), '{:.0f}', ' M€'):>13}")
    out.append(f"  xG / xGA (reciente)   {_xg(pl):>13} {_xg(pv):>13}")
    out.append(f"  Córners (prom.)       {_val(pl.get('corners_favor'), '{:.1f}'):>13} {_val(pv.get('corners_favor'), '{:.1f}'):>13}")
    out.append(f"  Tarjetas (prom.)      {_val(pl.get('tarjetas_partido'), '{:.2f}'):>13} {_val(pv.get('tarjetas_partido'), '{:.2f}'):>13}")

    if ctx and ctx.get("standings"):
        out.append("")
        out.append(f"  TABLA GRUPO {ctx['grupo']}        PJ  Pts   GF:GC")
        for s in ctx["standings"]:
            marca = "->" if s["fifa_code"] in (a.local, a.visita) else "  "
            out.append(f"  {marca} {s['nombre'][:18]:18}  {s['jugados']}   {s['puntos']:>3}   {s['goles_favor']}:{s['goles_contra']}")

    out.append("")
    out.append("  PRONÓSTICO              modelo  mercado  apostar   cuota      EV")
    clave = {"1": a.local, "X": "X", "2": a.visita}
    for sel, etq in (("1", f"Gana {cl}"), ("X", "Empate"), ("2", f"Gana {cv}")):
        pin = f"{a.novig[sel] * 100:.1f}%" if sel in a.novig else "—"
        cu = a.cuotas.get(clave[sel])
        evtxt = (f"{ev(a.trabajo[sel], cu):+.2f}" if a.fiable else "n/f") if cu else "—"
        out.append(f"  {etq:18}    {a.modelo[sel] * 100:5.1f}%  {pin:>7}   {a.trabajo[sel] * 100:5.1f}%  {(f'{cu:.2f}' if cu else '—'):>6}  {evtxt:>6}")

    out.append("")
    out.append("  GOLES")
    out.append(f"    Esperados: {a.lh + a.la:.1f}   ({cl} {a.lh:.1f} - {a.la:.1f} {cv})")
    out.append(f"    Over 2.5: {a.prob['over25'] * 100:.0f}%    Under 2.5: {a.prob['under25'] * 100:.0f}%")
    out.append(f"    Ambos anotan:  Sí {a.prob['btts_si'] * 100:.0f}%    No {a.prob['btts_no'] * 100:.0f}%")

    if a.corners_esp or a.tarjetas_esp:
        out.append("")
        out.append("  CÓRNERS Y TARJETAS")
        if a.corners_esp:
            o = over_under(a.corners_esp, [8.5, 9.5, 10.5])
            out.append(f"    Córners esperados: {a.corners_esp:.1f}   (" + "  ".join(f"O{l}: {p * 100:.0f}%" for l, p in o.items()) + ")")
        if a.tarjetas_esp:
            o = over_under(a.tarjetas_esp, [2.5, 3.5, 4.5])
            out.append(f"    Tarjetas esperadas: {a.tarjetas_esp:.1f}   (" + "  ".join(f"O{l}: {p * 100:.0f}%" for l, p in o.items()) + ")")

    out.append("")
    out.append(f"  CONFIANZA: {confianza}")
    if a.novig and not a.fiable:
        out.append(f"  [!] El modelo difiere {a.divergencia * 100:.0f}pp del mercado: NO fiable, no apostar por esta diferencia.")
    out.append("-" * anc)
    out.append("  Leyenda: EV = valor (+ conviene, - no, n/f = no fiable).")
    out.append("  Over 9.5 = 10 o más.  Glosario completo: opción 10 del menú.")
    out.append("=" * anc)
    return "\n".join(out)


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

    if a.corners_esp or a.tarjetas_esp:
        out.append("\n## Mercados secundarios (Footystats)\n")
        if a.corners_esp:
            ou = over_under(a.corners_esp, [8.5, 9.5, 10.5, 11.5])
            out.append(f"- Córners esperados: **{a.corners_esp:.1f}** · " + " · ".join(f"O{l} {p * 100:.0f}%" for l, p in ou.items()))
        if a.tarjetas_esp:
            ou = over_under(a.tarjetas_esp, [2.5, 3.5, 4.5, 5.5])
            out.append(f"- Tarjetas esperadas: **{a.tarjetas_esp:.1f}** · " + " · ".join(f"O{l} {p * 100:.0f}%" for l, p in ou.items()))

    out.append(f"\n**Confianza del análisis:** {confianza}")
    if a.novig and not a.fiable:
        out.append(f"\n> ⚠ El modelo diverge {a.divergencia * 100:.0f}pp del mercado sharp: EV no válido (probable fallo del modelo, no valor). No apostar por esta discrepancia.")
    out.append("\n*Herramienta de análisis, no recomendación de apuesta. El fútbol tiene varianza irreducible.*")
    return "\n".join(out)
