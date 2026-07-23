from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.ligas import codigo_para_modelo
from src.modelo import clubes as modelo_clubes
from src.modelo.dixon_coles import Ajustes, ParametrosModelo, corregir_empate_matriz, lambdas, matriz_marcadores, mercados
from src.modelo.estilos import cargar as cargar_estilos
from src.modelo.fuerzas import cargar as cargar_fuerzas
from src.modelo.fuerzas import lambdas_desde_fuerzas
from src.modelo.parametros import HOSTS
from src.modelo.parametros import cargar as cargar_par
from src.modelo.secundarios import over_under, over_under_nb
from src.modelo.valor import ev, mezclar_1x2, sin_vig

UMBRAL_DIVERGENCIA = 0.18
W_MERCADO_RENIDO = 0.80
W_MERCADO_GOLES = 0.80
W_MERCADO_CLUB = 0.65
K_PRIOR_WC = 3.0
K_PRIOR_CLUB = 10.0


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
    rho: float = 0.0
    saques_local: float | None = None
    saques_visita: float | None = None
    tarjetas_ratio_var: float = 1.0
    n_wc: int = 0
    goles_mercado: dict = field(default_factory=dict)
    btts_mercado: dict = field(default_factory=dict)


def _stats_wc(conn: sqlite3.Connection, equipo_id: int) -> dict | None:
    try:
        fila = conn.execute(
            "SELECT COUNT(*) n, AVG(e.amarillas + e.rojas) tarjetas, AVG(e.saques_meta) saques, "
            "AVG(e.xg) xg, AVG(riv.xg) xga, AVG(t.corners_total) corners_total "
            "FROM estadisticas_mundial e JOIN "
            "(SELECT partido_id, SUM(corners) corners_total FROM estadisticas_mundial GROUP BY partido_id) t "
            "ON t.partido_id = e.partido_id "
            "JOIN estadisticas_mundial riv ON riv.partido_id = e.partido_id AND riv.equipo_id != e.equipo_id "
            "WHERE e.equipo_id = ?",
            (equipo_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(fila) if fila and fila["n"] else None


def _medias_torneo(conn: sqlite3.Connection) -> dict | None:
    try:
        filas = conn.execute(
            "SELECT SUM(amarillas + rojas) tarjetas, SUM(saques_meta) saques FROM estadisticas_mundial GROUP BY partido_id"
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    if not filas:
        return None
    tarjetas = [f["tarjetas"] for f in filas]
    m = sum(tarjetas) / len(tarjetas)
    var = sum((t - m) ** 2 for t in tarjetas) / max(len(tarjetas) - 1, 1)
    saques = sum(f["saques"] for f in filas) / (2 * len(filas))
    return {"tarjetas_ratio_var": (var / m if m > 0 else 1.0), "saques_equipo": saques}


def _mezcla(prior: float | None, obs: float | None, n: float) -> float | None:
    if obs is None:
        return prior
    if prior is None:
        return obs
    return (n * obs + K_PRIOR_WC * prior) / (n + K_PRIOR_WC)


def _dist_total(matriz: np.ndarray) -> np.ndarray:
    n = matriz.shape[0]
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    return np.bincount((i + j).ravel(), weights=matriz.ravel())


def _pesos_over(dist: np.ndarray, linea: float) -> tuple[float, float]:
    cuartos = round(linea * 4)
    if cuartos % 4 == 2:
        a = float(dist[int(linea) + 1:].sum())
        return a, 1.0 - a
    if cuartos % 4 == 0:
        entera = int(round(linea))
        return float(dist[entera + 1:].sum()), float(dist[:entera].sum())
    a1, b1 = _pesos_over(dist, linea - 0.25)
    a2, b2 = _pesos_over(dist, linea + 0.25)
    return (a1 + a2) / 2.0, (b1 + b2) / 2.0


def _linea_principal(totals: dict[str, float], objetivo: float):
    lineas: dict[float, dict[str, float]] = {}
    for sel, cuota in totals.items():
        lado = "over" if sel.startswith("over") else ("under" if sel.startswith("under") else None)
        if lado is None:
            continue
        try:
            linea = float(sel[len(lado):])
        except ValueError:
            continue
        lineas.setdefault(linea, {})[lado] = cuota
    completas = {l: c for l, c in lineas.items() if len(c) == 2}
    if not completas:
        return None
    linea = min(completas, key=lambda l: abs(l - objetivo))
    return linea, completas[linea]


def _mercado_dos_lados(modelo: dict[str, float], cuotas: dict[str, float], masa: float = 1.0, extra: dict | None = None) -> dict:
    novig = sin_vig(cuotas)
    trabajo = {k: (1.0 - W_MERCADO_GOLES) * modelo[k] + W_MERCADO_GOLES * novig[k] for k in modelo}
    lado = next(iter(modelo))
    divergencia = abs(modelo[lado] - novig[lado])
    evs = {k: masa * (trabajo[k] * (cuotas[k] - 1.0) - (1.0 - trabajo[k])) for k in modelo}
    out = {
        "modelo": modelo,
        "cuotas": cuotas,
        "novig": novig,
        "trabajo": trabajo,
        "ev": evs,
        "divergencia": divergencia,
        "fiable": divergencia <= UMBRAL_DIVERGENCIA,
    }
    if extra:
        out.update(extra)
    return out


def analizar_1x2(conn: sqlite3.Connection, data_dir: Path, local: str, visita: str, ajustes: Ajustes | None = None) -> Analisis | None:
    eq = {
        r["fifa_code"]: r
        for r in conn.execute(
            "SELECT id, fifa_code, nombre, confederacion, elo, api_football_id, valor_plantilla, "
            "xg_fs, xga_fs, corners_favor, tarjetas_partido, estilo FROM equipos"
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

    matriz = corregir_empate_matriz(matriz_marcadores(lh, la, par), delta)
    prob = mercados(matriz)
    modelo = {"1": prob["1"], "X": prob["X"], "2": prob["2"]}
    if max(modelo["1"], modelo["2"]) < 0.45:
        w_mercado = max(w_mercado, W_MERCADO_RENIDO)

    partido = conn.execute(
        "SELECT p.id FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id WHERE el.fifa_code=? AND ev.fifa_code=?",
        (local, visita),
    ).fetchone()
    por_mercado: dict[str, dict[str, float]] = {}
    if partido:
        for r in conn.execute(
            "SELECT mercado, seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle'",
            (partido["id"],),
        ):
            por_mercado.setdefault(r["mercado"], {})[r["seleccion"]] = r["cuota"]
    cuotas = por_mercado.get("1X2", {})

    goles_mercado: dict = {}
    linea_ppal = _linea_principal(por_mercado.get("totals", {}), lh + la)
    if linea_ppal:
        ou_linea, ou_cuotas = linea_ppal
        a_over, b_over = _pesos_over(_dist_total(matriz), ou_linea)
        masa = a_over + b_over
        q_over = a_over / masa if masa > 0 else 0.5
        goles_mercado = _mercado_dos_lados(
            {"over": q_over, "under": 1.0 - q_over}, ou_cuotas, masa=masa, extra={"linea": ou_linea}
        )

    btts_mercado: dict = {}
    btts_cuotas = por_mercado.get("btts", {})
    if {"si", "no"} <= btts_cuotas.keys():
        btts_mercado = _mercado_dos_lados(
            {"si": prob["btts_si"], "no": prob["btts_no"]},
            {"si": btts_cuotas["si"], "no": btts_cuotas["no"]},
        )

    clave = {"1": local, "X": "X", "2": visita}
    novig = sin_vig({s: cuotas[clave[s]] for s in ("1", "X", "2")}) if len(cuotas) >= 3 else {}
    trabajo = mezclar_1x2(modelo, novig, w_mercado) if novig else modelo
    divergencia = max(abs(modelo[s] - novig[s]) for s in ("1", "X", "2")) if novig else 0.0
    fiable = divergencia <= UMBRAL_DIVERGENCIA

    cl, cv = eq[local]["corners_favor"], eq[visita]["corners_favor"]
    tl, tv = eq[local]["tarjetas_partido"], eq[visita]["tarjetas_partido"]
    wc_l, wc_v = _stats_wc(conn, eq[local]["id"]), _stats_wc(conn, eq[visita]["id"])
    medias = _medias_torneo(conn)

    prior_corners = (cl + cv) / 2 if (cl and cv) else None
    obs_corners, n_corners = None, 0.0
    if wc_l and wc_v:
        obs_corners = (wc_l["corners_total"] + wc_v["corners_total"]) / 2
        n_corners = (wc_l["n"] + wc_v["n"]) / 2
    corners_esp = _mezcla(prior_corners, obs_corners, n_corners)

    tarj_l = _mezcla(tl, wc_l["tarjetas"] if wc_l else None, wc_l["n"] if wc_l else 0.0)
    tarj_v = _mezcla(tv, wc_v["tarjetas"] if wc_v else None, wc_v["n"] if wc_v else 0.0)
    tarjetas_esp = (tarj_l + tarj_v) if (tarj_l and tarj_v) else None

    saques_l = saques_v = None
    if medias:
        base_saques = medias["saques_equipo"]
        saques_l = _mezcla(base_saques, wc_l["saques"] if wc_l else None, wc_l["n"] if wc_l else 0.0)
        saques_v = _mezcla(base_saques, wc_v["saques"] if wc_v else None, wc_v["n"] if wc_v else 0.0)

    estilos = cargar_estilos(data_dir)
    perfil_l, perfil_v = dict(eq[local]), dict(eq[visita])
    for code, perfil, wc in ((local, perfil_l, wc_l), (visita, perfil_v, wc_v)):
        if wc:
            perfil["xg_wc"], perfil["xga_wc"] = wc["xg"], wc["xga"]
        info = (estilos or {}).get("equipos", {}).get(code)
        if info:
            perfil["estilo_nota"] = info.get("nota")

    return Analisis(
        local, visita, eq[local]["nombre"], eq[visita]["nombre"], metodo, lh, la,
        prob, modelo, novig, trabajo, cuotas, fiable, divergencia, matriz, corners_esp, tarjetas_esp,
        perfil_l, perfil_v,
        rho=par.rho,
        saques_local=saques_l,
        saques_visita=saques_v,
        tarjetas_ratio_var=medias["tarjetas_ratio_var"] if medias else 1.0,
        n_wc=int(min(wc_l["n"] if wc_l else 0, wc_v["n"] if wc_v else 0)),
        goles_mercado=goles_mercado,
        btts_mercado=btts_mercado,
    )


def _stats_club(conn: sqlite3.Connection, liga_codigo: str, nombre: str) -> dict | None:
    fila = conn.execute(
        "SELECT AVG(corners) corners, AVG(tarjetas) tarjetas, COUNT(*) n FROM ("
        "  SELECT (corners_local+corners_visita) corners, (amarillas_local+rojas_local+amarillas_visita+rojas_visita) tarjetas "
        "  FROM partidos_club pc JOIN ligas l ON pc.liga_id=l.id WHERE l.codigo=? AND pc.local=? "
        "  UNION ALL "
        "  SELECT (corners_local+corners_visita), (amarillas_local+rojas_local+amarillas_visita+rojas_visita) "
        "  FROM partidos_club pc JOIN ligas l ON pc.liga_id=l.id WHERE l.codigo=? AND pc.visita=?"
        ")",
        (liga_codigo, nombre, liga_codigo, nombre),
    ).fetchone()
    if fila is None or not fila["n"] or fila["corners"] is None or fila["tarjetas"] is None:
        return None
    return {"corners_total": fila["corners"], "tarjetas_total": fila["tarjetas"], "n": fila["n"]}


def analizar_club(conn: sqlite3.Connection, data_dir: Path, liga_codigo: str, local: str, visita: str) -> Analisis | None:
    liga_codigo = codigo_para_modelo(liga_codigo)
    eq = {
        r["fifa_code"]: r
        for r in conn.execute(
            "SELECT id, fifa_code, nombre, fd_uk_nombre FROM equipos WHERE fifa_code IN (?, ?)",
            (local, visita),
        )
    }
    if local not in eq or visita not in eq:
        return None

    fuerzas = modelo_clubes.cargar(data_dir, liga_codigo)
    if fuerzas is None:
        return None
    nombre_l = eq[local]["fd_uk_nombre"] or eq[local]["nombre"]
    nombre_v = eq[visita]["fd_uk_nombre"] or eq[visita]["nombre"]
    res = modelo_clubes.lambdas(fuerzas, nombre_l, nombre_v)
    if res is None:
        return None
    lh, la = res

    par = ParametrosModelo(tasa_base=0.0, rho=fuerzas["rho"])
    matriz = matriz_marcadores(lh, la, par)
    prob = mercados(matriz)
    modelo = {"1": prob["1"], "X": prob["X"], "2": prob["2"]}
    w_mercado = W_MERCADO_RENIDO if max(modelo["1"], modelo["2"]) < 0.45 else W_MERCADO_CLUB

    partido = conn.execute(
        "SELECT p.id FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id WHERE el.fifa_code=? AND ev.fifa_code=?",
        (local, visita),
    ).fetchone()
    por_mercado: dict[str, dict[str, float]] = {}
    if partido:
        for r in conn.execute(
            "SELECT mercado, seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle'",
            (partido["id"],),
        ):
            por_mercado.setdefault(r["mercado"], {})[r["seleccion"]] = r["cuota"]
    cuotas = por_mercado.get("1X2", {})

    goles_mercado: dict = {}
    linea_ppal = _linea_principal(por_mercado.get("totals", {}), lh + la)
    if linea_ppal:
        ou_linea, ou_cuotas = linea_ppal
        a_over, b_over = _pesos_over(_dist_total(matriz), ou_linea)
        masa = a_over + b_over
        q_over = a_over / masa if masa > 0 else 0.5
        goles_mercado = _mercado_dos_lados(
            {"over": q_over, "under": 1.0 - q_over}, ou_cuotas, masa=masa, extra={"linea": ou_linea}
        )

    btts_mercado: dict = {}
    btts_cuotas = por_mercado.get("btts", {})
    if {"si", "no"} <= btts_cuotas.keys():
        btts_mercado = _mercado_dos_lados(
            {"si": prob["btts_si"], "no": prob["btts_no"]},
            {"si": btts_cuotas["si"], "no": btts_cuotas["no"]},
        )

    clave = {"1": local, "X": "X", "2": visita}
    novig = sin_vig({s: cuotas[clave[s]] for s in ("1", "X", "2")}) if len(cuotas) >= 3 else {}
    trabajo = mezclar_1x2(modelo, novig, w_mercado) if novig else modelo
    divergencia = max(abs(modelo[s] - novig[s]) for s in ("1", "X", "2")) if novig else 0.0
    fiable = divergencia <= UMBRAL_DIVERGENCIA

    st_l, st_v = _stats_club(conn, liga_codigo, nombre_l), _stats_club(conn, liga_codigo, nombre_v)
    corners_esp = (st_l["corners_total"] + st_v["corners_total"]) / 2 if (st_l and st_v) else None
    tarj_l = st_l["tarjetas_total"] / 2 if st_l else None
    tarj_v = st_v["tarjetas_total"] / 2 if st_v else None
    tarjetas_esp = (tarj_l + tarj_v) if (tarj_l and tarj_v) else None

    return Analisis(
        local, visita, eq[local]["nombre"], eq[visita]["nombre"], "clubes", lh, la,
        prob, modelo, novig, trabajo, cuotas, fiable, divergencia, matriz, corners_esp, tarjetas_esp,
        dict(eq[local]), dict(eq[visita]),
        rho=par.rho,
        goles_mercado=goles_mercado,
        btts_mercado=btts_mercado,
    )


def contexto_partido(conn: sqlite3.Connection, local: str, visita: str) -> dict | None:
    row = conn.execute(
        "SELECT p.fecha, p.fase, p.grupo, p.estado, p.arbitro, l.codigo liga_codigo, l.nombre liga_nombre "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id "
        "LEFT JOIN ligas l ON p.liga_id=l.id "
        "WHERE el.fifa_code=? AND ev.fifa_code=?",
        (local, visita),
    ).fetchone()
    if row is None:
        return None
    grupo = row["grupo"] or row["liga_codigo"]
    standings = conn.execute(
        "SELECT s.posicion, e.fifa_code, e.nombre, s.jugados, s.puntos, s.goles_favor, s.goles_contra, s.diferencia "
        "FROM standings s JOIN equipos e ON s.equipo_id=e.id WHERE s.grupo=? ORDER BY s.posicion",
        (grupo,),
    ).fetchall()
    return {
        "fecha": row["fecha"], "fase": row["fase"], "grupo": grupo, "estado": row["estado"],
        "arbitro": row["arbitro"], "standings": standings, "liga_nombre": row["liga_nombre"],
    }


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


def _xg_wc(p: dict) -> str:
    if p.get("xg_wc") is not None and p.get("xga_wc") is not None:
        return f"{p['xg_wc']:.2f}/{p['xga_wc']:.2f}"
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
    out.append(f"  xG / xGA Mundial      {_xg_wc(pl):>13} {_xg_wc(pv):>13}")
    out.append(f"  Córners (prom.)       {_val(pl.get('corners_favor'), '{:.1f}'):>13} {_val(pv.get('corners_favor'), '{:.1f}'):>13}")
    out.append(f"  Tarjetas (prom.)      {_val(pl.get('tarjetas_partido'), '{:.2f}'):>13} {_val(pv.get('tarjetas_partido'), '{:.2f}'):>13}")

    if pl.get("estilo") or pv.get("estilo"):
        out.append("")
        out.append("  ESTILO (datos del Mundial + prensa)")
        for nombre, p in ((nl, pl), (nv, pv)):
            if p.get("estilo"):
                out.append(f"    {nombre}: {p['estilo']}")

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
    for titulo, g, etiquetas in (
        ("Línea de goles vs Pinnacle", a.goles_mercado,
         {"over": "Over", "under": "Under"}),
        ("Ambos anotan vs Pinnacle", a.btts_mercado, {"si": "Sí", "no": "No"}),
    ):
        if not g:
            continue
        sufijo = f" {g['linea']}" if "linea" in g else ""
        out.append(f"    {titulo}:")
        for lado, etq in etiquetas.items():
            cu = g["cuotas"][lado]
            evtxt = f"{g['ev'][lado]:+.2f}" if g["fiable"] else "n/f"
            out.append(
                f"      {etq + sufijo:11} modelo {g['modelo'][lado] * 100:5.1f}%  mercado {g['novig'][lado] * 100:5.1f}%  "
                f"apostar {g['trabajo'][lado] * 100:5.1f}%  cuota {cu:.2f}  EV {evtxt}"
            )

    if a.corners_esp or a.tarjetas_esp or a.saques_local:
        out.append("")
        out.append("  CÓRNERS, TARJETAS Y SAQUES DE META")
        if a.corners_esp:
            o = over_under(a.corners_esp, [8.5, 9.5, 10.5])
            out.append(f"    Córners esperados: {a.corners_esp:.1f}   (" + "  ".join(f"O{l}: {p * 100:.0f}%" for l, p in o.items()) + ")")
        if a.tarjetas_esp:
            o = over_under_nb(a.tarjetas_esp, a.tarjetas_ratio_var, [2.5, 3.5, 4.5])
            out.append(f"    Tarjetas esperadas: {a.tarjetas_esp:.1f}   (" + "  ".join(f"O{l}: {p * 100:.0f}%" for l, p in o.items()) + ")")
        if a.saques_local and a.saques_visita:
            tot = a.saques_local + a.saques_visita
            o = over_under(tot, [13.5, 15.5, 17.5])
            out.append(f"    Saques de meta esperados: {tot:.1f}  ({cl} {a.saques_local:.1f} - {a.saques_visita:.1f} {cv})")
            out.append("      (" + "  ".join(f"O{l}: {p * 100:.0f}%" for l, p in o.items()) + ")")

    out.append("")
    out.append(f"  CONFIANZA: {confianza}")
    if a.novig and not a.fiable:
        out.append(f"  [!] El modelo difiere {a.divergencia * 100:.0f}pp del mercado: NO fiable, no apostar por esta diferencia.")
    out.append("-" * anc)
    out.append("  Leyenda: EV = valor (+ conviene, - no, n/f = no fiable).")
    out.append("  Over 9.5 = 10 o más.  Glosario completo: opción 9 del menú.")
    out.append("=" * anc)
    return "\n".join(out)


def narrativa(a: Analisis) -> str:
    pl, pv = a.perfil_local, a.perfil_visita
    nl, nv = a.nombre_local, a.nombre_visita
    p1, px, p2 = a.modelo["1"], a.modelo["X"], a.modelo["2"]
    lineas = []

    if max(p1, p2) < 0.45:
        lineas.append(f"**Partido parejo:** ninguno es claro favorito ({nl} {p1 * 100:.0f}%, empate {px * 100:.0f}%, {nv} {p2 * 100:.0f}%).")
    else:
        favn, favp, ofa, ori = (nl, p1, pl, pv) if p1 > p2 else (nv, p2, pv, pl)
        razones = []
        if ofa.get("elo") and ori.get("elo") and ofa["elo"] - ori["elo"] > 60:
            razones.append(f"bastante más Elo ({int(ofa['elo'])} frente a {int(ori['elo'])})")
        if ofa.get("valor_plantilla") and ori.get("valor_plantilla") and ofa["valor_plantilla"] > ori["valor_plantilla"] * 1.4:
            razones.append(f"una plantilla más cara ({ofa['valor_plantilla']:.0f} vs {ori['valor_plantilla']:.0f} M€)")
        if ofa.get("xg_fs") and ori.get("xg_fs") and ofa["xg_fs"] > ori["xg_fs"] + 0.4:
            razones.append("mejor xG reciente")
        motivo = ", ".join(razones) if razones else "su mejor rendimiento general"
        lineas.append(f"**{favn} es favorito** ({favp * 100:.0f}%), sobre todo por {motivo}.")

    tot = a.lh + a.la
    if tot < 2.3:
        lineas.append(f"Se esperan **pocos goles** (~{tot:.1f}), por eso domina el **Under 2.5** ({a.prob['under25'] * 100:.0f}%).")
    elif tot > 2.9:
        lineas.append(f"Se esperan **muchos goles** (~{tot:.1f}), lo que favorece el **Over 2.5** ({a.prob['over25'] * 100:.0f}%).")
    else:
        lineas.append(f"Goles esperados cerca de la media (~{tot:.1f}); Over 2.5 al {a.prob['over25'] * 100:.0f}%.")

    if a.prob["btts_si"] < 0.4:
        lineas.append(f"El **'ambos anotan' es poco probable** ({a.prob['btts_si'] * 100:.0f}%): se espera que uno de los dos no marque.")
    elif a.prob["btts_si"] > 0.55:
        lineas.append(f"Buena chance de que **ambos marquen** ({a.prob['btts_si'] * 100:.0f}%).")

    if a.corners_esp and a.tarjetas_esp:
        lineas.append(f"En **córners** se esperan ~{a.corners_esp:.0f} y en **tarjetas** ~{a.tarjetas_esp:.1f} (según promedios recientes).")

    if a.novig and a.fiable:
        clave = {"1": a.local, "X": "X", "2": a.visita}
        evs = {s: ev(a.trabajo[s], a.cuotas[clave[s]]) for s in ("1", "X", "2") if a.cuotas.get(clave[s])}
        mejor = max(evs, key=evs.get) if evs else None
        if mejor and evs[mejor] > 0.02:
            etq = {"1": nl, "X": "el empate", "2": nv}[mejor]
            lineas.append(f"Frente al mercado, la opción con algo de **valor** sería **{etq}** (EV {evs[mejor]:+.2f}).")
        else:
            lineas.append("Frente al mercado, **ninguna opción ofrece valor claro**: las cuotas ya reflejan bien las probabilidades.")
    elif a.novig and not a.fiable:
        lineas.append("El modelo **difiere mucho del mercado** aquí: se considera poco fiable y no conviene apostar por esa diferencia.")

    return "\n\n".join(lineas)


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

    if a.perfil_local.get("estilo") or a.perfil_visita.get("estilo"):
        out.append("\n## Estilo de juego (datos del Mundial + prensa)\n")
        for p, nombre in ((a.perfil_local, a.nombre_local), (a.perfil_visita, a.nombre_visita)):
            if p.get("estilo"):
                out.append(f"- **{nombre}** ({_xg_wc(p)} xG/xGA en el Mundial): {p['estilo']}")
                if p.get("estilo_nota"):
                    out.append(f"  - {p['estilo_nota']}")

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

    if a.goles_mercado or a.btts_mercado:
        out.append("\n### Goles vs mercado (Pinnacle)\n")
        out.append("| Mercado | Modelo | Pinnacle | Trabajo | Cuota | EV |")
        out.append("|---|---|---|---|---|---|")
        pares = []
        if a.goles_mercado:
            g = a.goles_mercado
            pares += [(f"Más de {g['linea']} goles", g, "over"), (f"Menos de {g['linea']} goles", g, "under")]
        if a.btts_mercado:
            pares += [("Ambos anotan: Sí", a.btts_mercado, "si"), ("Ambos anotan: No", a.btts_mercado, "no")]
        for etq, g, lado in pares:
            cu = g["cuotas"][lado]
            evv = f"{g['ev'][lado]:+.3f}" if g["fiable"] else "n/f"
            out.append(
                f"| {etq} | {g['modelo'][lado] * 100:.1f}% | {g['novig'][lado] * 100:.1f}% | "
                f"{g['trabajo'][lado] * 100:.1f}% | {cu:.2f} | {evv} |"
            )
        no_fiables = [g for g in (a.goles_mercado, a.btts_mercado) if g and not g["fiable"]]
        if no_fiables:
            out.append("\n> ⚠ En los mercados marcados n/f el modelo diverge demasiado del mercado: EV no válido.")

    if a.corners_esp or a.tarjetas_esp or a.saques_local:
        fuente_sec = "Footystats + partidos reales del Mundial" if a.n_wc else "Footystats"
        out.append(f"\n## Mercados secundarios ({fuente_sec})\n")
        if a.corners_esp:
            ou = over_under(a.corners_esp, [8.5, 9.5, 10.5, 11.5])
            out.append(f"- Córners esperados: **{a.corners_esp:.1f}** · " + " · ".join(f"O{l} {p * 100:.0f}%" for l, p in ou.items()))
        if a.tarjetas_esp:
            ou = over_under_nb(a.tarjetas_esp, a.tarjetas_ratio_var, [2.5, 3.5, 4.5, 5.5])
            out.append(f"- Tarjetas esperadas: **{a.tarjetas_esp:.1f}** · " + " · ".join(f"O{l} {p * 100:.0f}%" for l, p in ou.items()))
        if a.saques_local and a.saques_visita:
            tot = a.saques_local + a.saques_visita
            ou = over_under(tot, [13.5, 15.5, 17.5])
            out.append(
                f"- Saques de meta esperados: **{tot:.1f}** ({a.nombre_local} {a.saques_local:.1f} · {a.nombre_visita} {a.saques_visita:.1f}) · "
                + " · ".join(f"O{l} {p * 100:.0f}%" for l, p in ou.items())
            )

    out.append(f"\n**Confianza del análisis:** {confianza}")
    if a.novig and not a.fiable:
        out.append(f"\n> ⚠ El modelo diverge {a.divergencia * 100:.0f}pp del mercado sharp: EV no válido (probable fallo del modelo, no valor). No apostar por esta discrepancia.")
    out.append("\n*Herramienta de análisis, no recomendación de apuesta. El fútbol tiene varianza irreducible.*")
    return "\n".join(out)
