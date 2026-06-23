from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from src.config import load_config
from src.db.database import connect
from src.modelo.bet_builder import prob_conjunta, prob_marginal
from src.modelo.dixon_coles import Ajustes
from src.modelo.secundarios import over_under
from src.modelo.valor import ev
from src.plantillas import detectar_ausencias, multiplicadores
from src.reporte import analizar_1x2, contexto_partido, narrativa, nivel_confianza

st.set_page_config(page_title="Botano · Mundial 2026", page_icon="⚽", layout="wide")
CFG = load_config()


@st.cache_data(show_spinner=False)
def cargar_equipos():
    conn = connect(CFG.db_path)
    filas = conn.execute("SELECT fifa_code, nombre FROM equipos ORDER BY nombre").fetchall()
    conn.close()
    return {f"{r['nombre']} ({r['fifa_code']})": r["fifa_code"] for r in filas}


EQUIPOS = cargar_equipos()
NOMBRES = list(EQUIPOS)
MERCADOS_COMBI = {
    "Gana local": ("g", "1"),
    "Empate": ("g", "X"),
    "Gana visita": ("g", "2"),
    "Local o empate (1X)": ("g", "1X"),
    "Empate o visita (X2)": ("g", "X2"),
    "Local o visita, no empate (12)": ("g", "12"),
    "Ambos anotan": ("g", "btts"),
    "No ambos anotan": ("g", "nobtts"),
    "Más de 0.5 goles": ("g", "over0.5"),
    "Más de 1.5 goles": ("g", "over1.5"),
    "Menos de 1.5 goles": ("g", "under1.5"),
    "Más de 2.5 goles": ("g", "over2.5"),
    "Menos de 2.5 goles": ("g", "under2.5"),
    "Más de 3.5 goles": ("g", "over3.5"),
    "Menos de 3.5 goles": ("g", "under3.5"),
    "Más de 4.5 goles": ("g", "over4.5"),
    "Menos de 4.5 goles": ("g", "under4.5"),
    "Local marca +0.5": ("g", "loc0.5"),
    "Local marca +1.5": ("g", "loc1.5"),
    "Visita marca +0.5": ("g", "vis0.5"),
    "Visita marca +1.5": ("g", "vis1.5"),
    "Primer gol: local": ("pg", "l"),
    "Primer gol: visita": ("pg", "v"),
    "Primer gol: ninguno (0-0)": ("pg", "n"),
    "Más de 6.5 córners": ("c", 6.5, "o"),
    "Más de 7.5 córners": ("c", 7.5, "o"),
    "Menos de 7.5 córners": ("c", 7.5, "u"),
    "Más de 8.5 córners": ("c", 8.5, "o"),
    "Menos de 8.5 córners": ("c", 8.5, "u"),
    "Más de 9.5 córners": ("c", 9.5, "o"),
    "Menos de 9.5 córners": ("c", 9.5, "u"),
    "Más de 10.5 córners": ("c", 10.5, "o"),
    "Menos de 10.5 córners": ("c", 10.5, "u"),
    "Más de 11.5 córners": ("c", 11.5, "o"),
    "Más de 1.5 tarjetas": ("t", 1.5, "o"),
    "Más de 2.5 tarjetas": ("t", 2.5, "o"),
    "Menos de 2.5 tarjetas": ("t", 2.5, "u"),
    "Más de 3.5 tarjetas": ("t", 3.5, "o"),
    "Menos de 3.5 tarjetas": ("t", 3.5, "u"),
    "Más de 4.5 tarjetas": ("t", 4.5, "o"),
    "Menos de 4.5 tarjetas": ("t", 4.5, "u"),
    "Menos de 5.5 tarjetas": ("t", 5.5, "u"),
}


def _prob_partido_combi(a, mercados):
    goles = [m[1] for m in mercados if m[0] == "g"]
    p_corr = prob_conjunta(a.matriz, goles) if goles else 1.0
    p_naive = 1.0
    for g in goles:
        p_naive *= prob_marginal(a.matriz, g)
    extra = 1.0
    for m in mercados:
        if m[0] == "c" and a.corners_esp:
            ov = over_under(a.corners_esp, [m[1]])[m[1]]
            extra *= ov if m[2] == "o" else (1 - ov)
        elif m[0] == "t" and a.tarjetas_esp:
            ov = over_under(a.tarjetas_esp, [m[1]])[m[1]]
            extra *= ov if m[2] == "o" else (1 - ov)
        elif m[0] == "pg":
            pl, pv, sin = _primer_gol(a.lh, a.la, float(a.matriz[0, 0]))
            extra *= {"l": pl, "v": pv, "n": sin}[m[1]]
    return p_corr * extra, p_naive * extra


def _prob_individual(a, spec):
    if spec[0] == "g":
        return prob_marginal(a.matriz, spec[1])
    if spec[0] == "c" and a.corners_esp:
        ov = over_under(a.corners_esp, [spec[1]])[spec[1]]
        return ov if spec[2] == "o" else 1 - ov
    if spec[0] == "t" and a.tarjetas_esp:
        ov = over_under(a.tarjetas_esp, [spec[1]])[spec[1]]
        return ov if spec[2] == "o" else 1 - ov
    if spec[0] == "pg":
        pl, pv, sin = _primer_gol(a.lh, a.la, float(a.matriz[0, 0]))
        return {"l": pl, "v": pv, "n": sin}[spec[1]]
    return 1.0


def _desglose(pares):
    acum = 1.0
    filas = []
    for nombre, prob in pares:
        acum *= prob
        filas.append({"Selección": nombre, "Probabilidad": _pct(prob), "Prob. acumulada": _pct(acum)})
    return pd.DataFrame(filas)


FAMILIAS_PARLEY = {
    "Resultado": ["Gana local", "Gana visita", "Local o empate (1X)", "Empate o visita (X2)", "Local o visita, no empate (12)"],
    "Goles totales": ["Más de 1.5 goles", "Menos de 1.5 goles", "Más de 2.5 goles", "Menos de 2.5 goles", "Más de 3.5 goles", "Menos de 3.5 goles", "Menos de 4.5 goles"],
    "Ambos anotan": ["Ambos anotan", "No ambos anotan"],
    "Primer gol": ["Primer gol: local", "Primer gol: visita"],
    "Córners": [k for k in MERCADOS_COMBI if "córners" in k],
    "Tarjetas": [k for k in MERCADOS_COMBI if "tarjetas" in k],
}


def _parley_sugerido(a, umbral=0.68):
    seleccion = []
    for claves in FAMILIAS_PARLEY.values():
        cand = [(c, _prob_individual(a, MERCADOS_COMBI[c])) for c in claves if c in MERCADOS_COMBI]
        cand = [(c, p) for c, p in cand if p >= umbral]
        if cand:
            seleccion.append(max(cand, key=lambda x: x[1]))
    return seleccion


FAMILIAS_BB = dict(FAMILIAS_PARLEY)
FAMILIAS_BB["Goles local"] = ["Local marca +0.5", "Local marca +1.5"]
FAMILIAS_BB["Goles visita"] = ["Visita marca +0.5", "Visita marca +1.5"]


def _armar_bb_partido(a, cuota_min, total_min, n_min):
    cand = []
    for claves in FAMILIAS_BB.values():
        ops = [(c, _prob_individual(a, MERCADOS_COMBI[c])) for c in claves if c in MERCADOS_COMBI]
        ops = [(c, p) for c, p in ops if p > 0 and 1 / p > cuota_min]
        if ops:
            cand.append(max(ops, key=lambda x: x[1]))
    cand.sort(key=lambda x: -x[1])
    sel, prob, cuota = [], 0.0, 0.0
    for nombre, _p in cand:
        sel.append(nombre)
        prob, _ = _prob_partido_combi(a, [MERCADOS_COMBI[x] for x in sel])
        cuota = 1 / prob if prob > 0 else 0
        if len(sel) >= n_min and cuota > total_min:
            break
    filas = [{"Mercado": m, "Probabilidad": _pct(_prob_individual(a, MERCADOS_COMBI[m])),
              "Cuota justa": f"{1 / _prob_individual(a, MERCADOS_COMBI[m]):.2f}"} for m in sel]
    return filas, prob, cuota, len(sel), a.fiable


def _armar_bb_varios(prox, cuota_min, total_min, n_min):
    conn = connect(CFG.db_path)
    cand = []
    for p in prox:
        a = analizar_1x2(conn, CFG.data_dir, p["lf"], p["vf"])
        if a is None:
            continue
        ops = [(nombre, _prob_individual(a, spec)) for nombre, spec in MERCADOS_COMBI.items()]
        ops = [(nombre, pr) for nombre, pr in ops if 0 < pr < 0.667 and 1 / pr > cuota_min]
        if ops:
            best = max(ops, key=lambda x: x[1])
            cand.append({"Partido": f"{a.nombre_local} vs {a.nombre_visita}", "Mercado": best[0], "p": best[1], "fiable": a.fiable})
    conn.close()
    cand.sort(key=lambda x: -x["p"])
    sel, prob = [], 1.0
    for c in cand:
        sel.append(c)
        prob *= c["p"]
        if len(sel) >= n_min and 1 / prob > total_min:
            break
    cuota = 1 / prob if prob > 0 else 0
    fiable = all(c["fiable"] for c in sel)
    filas = [{"Partido": c["Partido"], "Mercado": c["Mercado"], "Probabilidad": _pct(c["p"]), "Cuota justa": f"{1 / c['p']:.2f}"} for c in sel]
    return filas, prob, cuota, len(sel), fiable


def _pct(x) -> str:
    return f"{x * 100:.1f}%" if x is not None else "—"


def _dist_goles(matriz):
    n = matriz.shape[0]
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    return np.bincount((i + j).ravel(), weights=matriz.ravel())


def _estilo(p) -> str:
    xg, xga = p.get("xg_fs"), p.get("xga_fs")
    if not xg or not xga:
        return "estilo no disponible"
    rasgos = []
    if xg >= 1.9:
        rasgos.append("muy ofensivo")
    elif xg >= 1.5:
        rasgos.append("ofensivo")
    elif xg < 1.1:
        rasgos.append("conservador en ataque")
    if xga <= 0.8:
        rasgos.append("sólido en defensa")
    elif xga >= 1.4:
        rasgos.append("frágil atrás")
    if xg + xga >= 3.0:
        rasgos.append("partidos abiertos")
    elif xg + xga <= 2.0:
        rasgos.append("partidos cerrados")
    return ", ".join(rasgos) if rasgos else "equilibrado"


def _over_equipo(matriz, eje: int, linea: float) -> float:
    marg = matriz.sum(axis=1) if eje == 0 else matriz.sum(axis=0)
    return float(marg[int(linea) + 1:].sum())


def _primer_gol(lh: float, la: float, p00: float):
    tot = lh + la
    if tot <= 0:
        return 0.0, 0.0, 1.0
    return (lh / tot) * (1 - p00), (la / tot) * (1 - p00), p00


def _lineas(centro: float, deltas=(-5.5, -2.5, 0.5, 3.5)) -> list[float]:
    c = round(centro)
    return [c + d for d in deltas if c + d > 0]


def _ajustes_por_bajas(local: str, visita: str):
    conn = connect(CFG.db_path)
    info = {
        r["fifa_code"]: dict(r)
        for r in conn.execute(
            "SELECT fifa_code, nombre, transfermarkt_id, football_data_id, valor_plantilla "
            "FROM equipos WHERE fifa_code IN (?, ?)",
            (local, visita),
        )
    }
    conn.close()
    detalle, fuera = [], {}
    for code in (local, visita):
        aus = detectar_ausencias(CFG, info[code]["transfermarkt_id"], info[code]["football_data_id"])
        fuera[code] = [n for n, _ in aus]
        if aus:
            detalle.append(f"**{info[code]['nombre']}**: " + ", ".join(f"{n} (€{v:.0f}m)" for n, v in aus[:5]))
    ml = multiplicadores(CFG, info[local]["transfermarkt_id"], info[local]["valor_plantilla"], fuera[local])
    mv = multiplicadores(CFG, info[visita]["transfermarkt_id"], info[visita]["valor_plantilla"], fuera[visita])
    aj = Ajustes(ataque_local=ml[0], defensa_local=ml[1], ataque_visita=mv[0], defensa_visita=mv[1])
    return aj, ("  ·  ".join(detalle) if detalle else "No se detectaron ausencias en la convocatoria.")


@st.cache_data(show_spinner=False)
def params_tiros():
    import json
    ruta = CFG.data_dir / "modelos" / "tiros.json"
    if ruta.exists():
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return d.get("xg_por_tiro", 0.108), d.get("ratio_al_arco", 0.32)
    return 0.108, 0.32


@st.cache_data(show_spinner="Consultando estadísticas del árbitro...")
def tasa_arbitro(nombre: str):
    if not nombre:
        return None
    try:
        from src.scrapers.transfermarkt import Transfermarkt
        return Transfermarkt(CFG.cache_dir).arbitro_tarjetas(nombre)
    except Exception:
        return None


def mostrar_analisis(a, ctx) -> None:
    arb_stats = tasa_arbitro(ctx.get("arbitro")) if ctx and ctx.get("arbitro") else None
    tarjetas_final = a.tarjetas_esp
    if a.tarjetas_esp and arb_stats:
        tarjetas_final = 0.5 * a.tarjetas_esp + 0.5 * arb_stats["amarillas_pp"]

    st.subheader(f"{a.nombre_local}  vs  {a.nombre_visita}")
    if ctx:
        fecha = ctx["fecha"][:16].replace("T", " ") if ctx["fecha"] else "?"
        arb = ""
        if ctx.get("arbitro"):
            arb = f" · Árbitro: {ctx['arbitro']}"
            if arb_stats:
                arb += f" ({arb_stats['amarillas_pp']:.1f} amarillas/partido)"
        st.caption(f"Grupo {ctx['grupo']} · {fecha} · {ctx['estado']}{arb}")

    izq, der = st.columns(2)
    pl, pv = a.perfil_local, a.perfil_visita

    def _xg(p):
        return f"{p['xg_fs']:.2f} / {p['xga_fs']:.2f}" if p.get("xg_fs") and p.get("xga_fs") else "—"

    perfil = pd.DataFrame(
        {
            a.nombre_local: [pl.get("elo"), pl.get("valor_plantilla"), _xg(pl), pl.get("corners_favor"), pl.get("tarjetas_partido")],
            a.nombre_visita: [pv.get("elo"), pv.get("valor_plantilla"), _xg(pv), pv.get("corners_favor"), pv.get("tarjetas_partido")],
            "Fuente": ["eloratings.net", "Transfermarkt", "Footystats", "Footystats", "Footystats"],
        },
        index=["Elo", "Valor plantilla (M€)", "xG / xGA", "Córners (prom.)", "Tarjetas (prom.)"],
    )
    izq.markdown("**Perfil de los equipos**")
    izq.table(perfil)
    izq.caption("Elo: sistema de puntos por resultados (eloratings.net). xG: goles esperados por calidad de ocasiones (Footystats).")

    if ctx and ctx.get("standings"):
        der.markdown(f"**Grupo {ctx['grupo']}**")
        der.dataframe(
            pd.DataFrame([{"Pos": s["posicion"], "Equipo": s["nombre"], "PJ": s["jugados"], "Pts": s["puntos"], "DG": s["diferencia"]} for s in ctx["standings"]]),
            hide_index=True, use_container_width=True,
        )
        der.caption("Resultados y tabla: football-data.org")

    st.caption(
        f"**Planteamiento esperado** (inferido del estilo de juego con datos reales, no declarado por el técnico): "
        f"{a.nombre_local} → _{_estilo(pl)}_  ·  {a.nombre_visita} → _{_estilo(pv)}_"
    )

    st.markdown("**Pronóstico (resultado del partido)**")
    clave = {"1": a.local, "X": "X", "2": a.visita}
    filas = []
    for sel, etq in (("1", f"Gana {a.nombre_local}"), ("X", "Empate"), ("2", f"Gana {a.nombre_visita}")):
        cu = a.cuotas.get(clave[sel])
        evtxt = (f"{ev(a.trabajo[sel], cu):+.3f}" if a.fiable else "n/f") if cu else "—"
        filas.append({
            "Resultado": etq, "Modelo": _pct(a.modelo[sel]), "Mercado": _pct(a.novig.get(sel)),
            "Apostar": _pct(a.trabajo[sel]), "Cuota": f"{cu:.2f}" if cu else "—", "EV": evtxt,
        })

    def color_ev(col):
        estilos = []
        for x in col:
            if isinstance(x, str) and x.startswith("+"):
                estilos.append("color: #1e8449; font-weight: bold")
            elif isinstance(x, str) and x.startswith("-"):
                estilos.append("color: #c0392b")
            else:
                estilos.append("color: gray")
        return estilos

    st.dataframe(pd.DataFrame(filas).style.apply(color_ev, subset=["EV"]), hide_index=True, use_container_width=True)
    st.caption(
        "**Cómo leer esto** · **Modelo**: probabilidad que estima el bot. "
        "**Mercado**: la misma probabilidad según la cuota de Pinnacle, quitándole el margen de la casa (fuente: The Odds API). "
        "**Apostar**: mezcla de las dos, es la que se usa para el valor. "
        "**EV (valor esperado)**: cuánto ganas/pierdes de media por cada €1 apostado a esa cuota — "
        "🟢 **positivo = hay valor** (candidato a apostar), 🔴 negativo = la cuota paga menos de lo justo, "
        "**n/f** = el modelo no es fiable en este partido (no apostar)."
    )
    if a.novig and not a.fiable:
        st.warning(f"El modelo difiere {a.divergencia * 100:.0f}pp del mercado: poco fiable, no apostar por esa diferencia.")

    st.markdown("**Doble oportunidad** (se cubren dos de los tres resultados)")
    d1, d2, d3 = st.columns(3)
    d1.metric(f"{a.nombre_local} o empate", _pct(a.modelo["1"] + a.modelo["X"]))
    d2.metric(f"Empate o {a.nombre_visita}", _pct(a.modelo["X"] + a.modelo["2"]))
    d3.metric(f"{a.nombre_local} o {a.nombre_visita}", _pct(a.modelo["1"] + a.modelo["2"]))
    st.caption("Sale de la **misma matriz Dixon-Coles** del modelo (no es una media): se suman las probabilidades de los dos resultados que cubre cada apuesta.")

    st.markdown("####  Interpretación")
    st.markdown(narrativa(a))

    st.markdown("####  Goles")
    g1, g2, g3 = st.columns(3)
    g1.metric("Goles esperados", f"{a.lh + a.la:.1f}")
    g1.caption(f"{a.nombre_local} {a.lh:.1f} - {a.la:.1f} {a.nombre_visita}")
    g2.metric("Over 2.5 goles", _pct(a.prob["over25"]))
    g3.metric("Ambos anotan", _pct(a.prob["btts_si"]))
    st.caption("Calculado por el **modelo Dixon-Coles** del bot (no es un dato de fuente externa): estima los goles de cada equipo y de ahí la probabilidad de cada marcador.")

    if a.corners_esp or a.tarjetas_esp:
        st.markdown("####  Córners y tarjetas")
        s1, s2 = st.columns(2)
        if a.corners_esp:
            o = over_under(a.corners_esp, [8.5, 9.5, 10.5])
            s1.metric("Córners esperados", f"{a.corners_esp:.1f}")
            s1.caption(" · ".join(f"+{l}: {_pct(p)}" for l, p in o.items()))
        if a.tarjetas_esp:
            o = over_under(tarjetas_final, [2.5, 3.5, 4.5])
            s2.metric("Tarjetas esperadas", f"{tarjetas_final:.1f}", "ajustado por el árbitro" if arb_stats else None)
            s2.caption(" · ".join(f"+{l}: {_pct(p)}" for l, p in o.items()))
        nota_arb = ", combinados con la **severidad del árbitro** (Transfermarkt)" if arb_stats else ""
        st.caption(f"Córners y tarjetas: modelo **Poisson** sobre los promedios de cada selección (Footystats){nota_arb}. '+9.5' = 10 o más.")

    st.markdown("####  Tiros (estimación a partir del xG)")
    k, ratio_arco = params_tiros()
    tiros_l, tiros_v = a.lh / k, a.la / k
    arco_l, arco_v = tiros_l * ratio_arco, tiros_v * ratio_arco
    z1, z2, z3 = st.columns(3)
    z1.metric(f"Tiros {a.nombre_local}", f"{tiros_l:.0f}", f"al arco ~{arco_l:.0f}")
    z2.metric(f"Tiros {a.nombre_visita}", f"{tiros_v:.0f}", f"al arco ~{arco_v:.0f}")
    z3.metric("Tiros totales", f"{tiros_l + tiros_v:.0f}", f"al arco ~{arco_l + arco_v:.0f}")
    zt, za = st.columns(2)
    ot = over_under(tiros_l + tiros_v, [x + 0.5 for x in range(12, 25)])
    zt.markdown("**Tiros totales (líneas)**")
    zt.dataframe(pd.DataFrame([{"Línea": l, "Más de": _pct(p), "Menos de": _pct(1 - p)} for l, p in ot.items()]), hide_index=True, use_container_width=True)
    oa = over_under(arco_l + arco_v, [x + 0.5 for x in range(2, 9)])
    za.markdown("**Tiros al arco totales (líneas)**")
    za.dataframe(pd.DataFrame([{"Línea": l, "Más de": _pct(p), "Menos de": _pct(1 - p)} for l, p in oa.items()]), hide_index=True, use_container_width=True)
    st.info(f"**Estimación** (no es un dato medido): tiros ≈ goles esperados ÷ {k:.3f} y al arco ≈ {ratio_arco * 100:.0f}% — **parámetros calibrados con los tiros reales del Mundial 2022 (StatsBomb)**, no inventados. Orientativo.")

    st.markdown("####  Probabilidades por línea (más de / menos de)")
    col_g, col_c, col_t = st.columns(3)
    dist = _dist_goles(a.matriz)
    col_g.markdown("**Goles totales**")
    col_g.table(pd.DataFrame([
        {"Línea": x, "Más de": _pct(float(dist[int(x) + 1:].sum())), "Menos de": _pct(1 - float(dist[int(x) + 1:].sum()))}
        for x in (0.5, 1.5, 2.5, 3.5, 4.5)
    ]))
    col_g.caption(f"Debido a que se esperan **{a.lh + a.la:.1f} goles** (ataque de {a.nombre_local} vs defensa de {a.nombre_visita} y viceversa): las líneas bajas son casi seguras y las altas caen rápido.")
    if a.corners_esp:
        oc = over_under(a.corners_esp, [3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5])
        col_c.markdown("**Córners totales**")
        col_c.dataframe(pd.DataFrame([{"Línea": l, "Más de": _pct(p), "Menos de": _pct(1 - p)} for l, p in oc.items()]), hide_index=True, use_container_width=True)
        col_c.caption(f"Debido al dominio esperado: {a.nombre_local} es _{_estilo(pl).split(',')[0]}_ y {a.nombre_visita} _{_estilo(pv).split(',')[0]}_; cuanto más ofensivo, más córners genera.")
    if a.tarjetas_esp:
        ot = over_under(tarjetas_final, [0.5, 1.5, 2.5, 3.5, 4.5, 5.5])
        col_t.markdown("**Tarjetas totales**")
        col_t.table(pd.DataFrame([{"Línea": l, "Más de": _pct(p), "Menos de": _pct(1 - p)} for l, p in ot.items()]))
        razon = f"árbitro **{ctx['arbitro']}** ({arb_stats['amarillas_pp']:.1f}/partido)" if (arb_stats and ctx) else "la intensidad del partido"
        col_t.caption(f"Debido a **{tarjetas_final:.1f} tarjetas** esperadas, influidas por {razon}.")

    st.markdown("####  Goles por equipo y primer gol")
    eq1, eq2, eq3 = st.columns(3)
    eq1.markdown(f"**{a.nombre_local} marca…**")
    eq1.table(pd.DataFrame([{"Goles": x, "Más de": _pct(_over_equipo(a.matriz, 0, x)), "Menos de": _pct(1 - _over_equipo(a.matriz, 0, x))} for x in (0.5, 1.5, 2.5, 3.5)]))
    eq2.markdown(f"**{a.nombre_visita} marca…**")
    eq2.table(pd.DataFrame([{"Goles": x, "Más de": _pct(_over_equipo(a.matriz, 1, x)), "Menos de": _pct(1 - _over_equipo(a.matriz, 1, x))} for x in (0.5, 1.5, 2.5, 3.5)]))
    p_local, p_visita, p_sin = _primer_gol(a.lh, a.la, float(a.matriz[0, 0]))
    eq3.markdown("**¿Quién marca primero?**")
    eq3.metric(a.nombre_local, _pct(p_local))
    eq3.metric(a.nombre_visita, _pct(p_visita))
    eq3.caption(f"Ningún gol: {_pct(p_sin)} · estimado por el ritmo goleador de cada equipo (modelo de Poisson en el tiempo).")

    tot = a.lh + a.la
    tend = "tiende a pocos goles" if tot < 2.3 else ("tiende a muchos goles" if tot > 2.9 else "tendencia media de goles")
    just = f"**Goles**: con {tot:.1f} esperados, el partido {tend}; por eso las líneas bajas son casi seguras y las altas caen rápido. "
    just += f"**Córners**: {a.nombre_local} es {_estilo(pl)} y {a.nombre_visita} es {_estilo(pv)} — cuanto más ofensivo y dominante, más córners. "
    just += f"**Tarjetas** (~{tarjetas_final:.1f} esperadas): suben con la intensidad y con el criterio del árbitro"
    if arb_stats:
        sev = "severo" if arb_stats["amarillas_pp"] >= 4.5 else ("permisivo" if arb_stats["amarillas_pp"] < 3.5 else "moderado")
        just += f" — **{ctx['arbitro']}** es {sev} ({arb_stats['amarillas_pp']:.1f} amarillas/partido), ya reflejado en la cifra."
    elif ctx and ctx.get("arbitro"):
        just += f" (designado: {ctx['arbitro']})."
    else:
        just += " (árbitro aún sin designar)."
    st.caption(just)

    st.info(f"Confianza del análisis: **{nivel_confianza(a)}**")

    parley = _parley_sugerido(a)
    if parley:
        st.markdown("#### 🎯 Parley sugerido (cada selección ≥ 68%)")
        st.table(pd.DataFrame([{"Selección": c, "Probabilidad": _pct(p), "Cuota mínima p/ valor": f"{1 / p:.2f}"} for c, p in parley]))
        p_parley, _ = _prob_partido_combi(a, [MERCADOS_COMBI[c] for c, _ in parley])
        pm1, pm2 = st.columns(2)
        pm1.metric("Probabilidad del parley", _pct(p_parley))
        pm2.metric("Cuota mínima del parley p/ valor", f"{1 / p_parley:.2f}" if p_parley > 0 else "—")
        st.caption(
            "Cada selección supera el 68% individualmente. La **cuota mínima** es la cuota justa (1÷probabilidad): "
            "por encima de ella hay valor. Si Betano paga **más** que la cuota mínima del parley, tiene EV positivo. "
            "Ojo: al combinarlas la probabilidad cae (se multiplican) y el riesgo sube — un parley largo rara vez conserva valor."
        )

    with st.expander("¿De dónde salen estos números? (fuentes y modelos)"):
        st.markdown(
            """
**Fuentes de los datos**
- **Elo** de selecciones → eloratings.net
- **Valor de plantilla** → Transfermarkt
- **xG/xGA, córners, tarjetas** → Footystats
- **Cuotas y mercado** (Pinnacle) → The Odds API
- **Resultados y tabla del grupo** → football-data.org
- **Histórico de selección 2022-24** (para entrenar el modelo) → API-Football

**Modelos estadísticos**
- **Goles → Dixon-Coles** (Poisson bivariado con corrección de marcadores bajos): estima los goles esperados de cada equipo (λ) y construye la probabilidad de cada marcador. De esa matriz salen 1X2, Over/Under y Ambos anotan, todos coherentes entre sí.
- **Fuerza de cada selección**: estimada de ~1.700 partidos (2022-24) con **ponderación temporal** (pesan más los recientes), **anclada al Elo** (compara entre confederaciones) y ajustada por el **valor de plantilla** (calibrado contra el mercado).
- **Mercado y valor**: la columna *Mercado* quita el margen de la casa a la cuota de Pinnacle (*no-vig*); *Apostar* mezcla modelo y mercado (*shrinkage*); el **EV** compara esa probabilidad con la cuota. Un **guardarraíl** marca "n/f" cuando el modelo se aleja demasiado del mercado.
- **Córners y tarjetas → Poisson** sobre los promedios de cada selección.
            """
        )


@st.cache_data(show_spinner=False)
def equipos_busqueda():
    from src.lector import ALIAS, _norm
    conn = connect(CFG.db_path)
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


@st.cache_data(ttl=600, show_spinner=False)
def proximos_partidos():
    from datetime import datetime, timedelta, timezone

    bog = timezone(timedelta(hours=-5))
    conn = connect(CFG.db_path)
    filas = conn.execute(
        "SELECT p.fecha, el.fifa_code lf, el.nombre ln, ev.fifa_code vf, ev.nombre vn "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id "
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
        if dia not in (0, 1):
            continue
        out.append({"dia": dia, "fecha": loc.strftime("%d/%m"), "hora": loc.strftime("%H:%M"),
                    "lf": r["lf"], "ln": r["ln"], "vf": r["vf"], "vn": r["vn"]})
    return out


st.sidebar.title("⚽ Botano")
st.sidebar.caption("Mundial 2026")
pagina = st.sidebar.radio("Menú", ["Analizar partido", "Analizar apuesta", "Armar Bet Builder", "Glosario"])
st.sidebar.caption("Herramienta de análisis, no garantía de ganancia.")


if pagina == "Analizar partido":
    st.title("Analizar partido")
    if "sb_local" not in st.session_state:
        st.session_state.sb_local = NOMBRES[0]
    if "sb_visita" not in st.session_state:
        st.session_state.sb_visita = NOMBRES[1]
    prox = proximos_partidos()
    if prox:
        st.markdown("**⚡ Partidos de hoy y mañana** — haz clic en uno y se rellenan los equipos (horario de Colombia):")
        for etiqueta, dnum in (("Hoy", 0), ("Mañana", 1)):
            deldia = [p for p in prox if p["dia"] == dnum]
            if not deldia:
                continue
            st.markdown(f"**{etiqueta}** · {deldia[0]['fecha']}")
            cols = st.columns(2)
            for i, p in enumerate(deldia):
                if cols[i % 2].button(f"🕐 {p['hora']} · {p['ln']} vs {p['vn']}", key=f"pb_{dnum}_{i}", use_container_width=True):
                    nl = next((n for n in NOMBRES if EQUIPOS[n] == p["lf"]), None)
                    nv = next((n for n in NOMBRES if EQUIPOS[n] == p["vf"]), None)
                    if nl:
                        st.session_state.sb_local = nl
                    if nv:
                        st.session_state.sb_visita = nv
    c1, c2 = st.columns(2)
    local = c1.selectbox("Local", NOMBRES, key="sb_local")
    visita = c2.selectbox("Visitante", NOMBRES, key="sb_visita")
    descontar = st.checkbox("Descontar bajas automáticamente (consulta internet)")
    if st.button("Analizar", type="primary"):
        l, v = EQUIPOS[local], EQUIPOS[visita]
        if l == v:
            st.error("Elige dos equipos distintos.")
        else:
            ajustes = None
            if descontar:
                with st.spinner("Buscando bajas en internet..."):
                    ajustes, detalle = _ajustes_por_bajas(l, v)
                st.info(f"Bajas detectadas — {detalle}")
            conn = connect(CFG.db_path)
            a = analizar_1x2(conn, CFG.data_dir, l, v, ajustes)
            ctx = contexto_partido(conn, l, v)
            conn.close()
            if a is None:
                st.error("No hay datos para ese partido.")
            else:
                mostrar_analisis(a, ctx)

elif pagina == "Analizar apuesta":
    st.title("Analizar apuesta")
    st.caption("Lee tu apuesta desde una captura de Betano (recomendado) o ármala a mano. "
               "Dentro de un mismo partido se usa la correlación real (matriz Dixon-Coles para goles); córners y tarjetas se tratan como independientes.")

    st.header("Analizar sencilla")
    st.caption("Una sola captura, de un mismo partido (uno o varios mercados).")
    from streamlit_paste_button import paste_image_button
    pegar = paste_image_button("📋 Pegar captura (Ctrl+V)", errors="ignore")
    archivo = st.file_uploader("…o sube el archivo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    imagen_bytes = None
    if pegar.image_data is not None:
        import io as _io
        _buf = _io.BytesIO()
        pegar.image_data.save(_buf, format="PNG")
        imagen_bytes = _buf.getvalue()
    elif archivo:
        imagen_bytes = archivo.getvalue()
    if imagen_bytes:
        import importlib

        import src.lector as _lector
        importlib.reload(_lector)
        analizar, ocr = _lector.analizar, _lector.ocr
        try:
            with st.spinner("Leyendo la imagen con OCR de Windows..."):
                texto = ocr(imagen_bytes)
        except Exception as exc:
            st.error(f"No se pudo leer la imagen: {exc}")
            texto = ""
        if texto:
            local, visita, detectados = analizar(texto, equipos_busqueda())
            with st.expander("Texto leído por el OCR (revisa si algo se detectó mal)"):
                st.text(texto)
            if not local or not visita:
                st.warning("No detecté dos equipos con claridad. Prueba con una captura más nítida o usa el modo manual de abajo.")
            else:
                st.success(f"Detectado: **{local[1]} vs {visita[1]}** · {len(detectados)} mercado(s)")
                cl = next((n for n in NOMBRES if EQUIPOS[n] == local[0]), NOMBRES[0])
                cv = next((n for n in NOMBRES if EQUIPOS[n] == visita[0]), NOMBRES[1])
                c1, c2 = st.columns(2)
                loc = c1.selectbox("Local", NOMBRES, index=NOMBRES.index(cl), key="cap_l")
                vis = c2.selectbox("Visitante", NOMBRES, index=NOMBRES.index(cv), key="cap_v")
                pre = [m for m in detectados if m in MERCADOS_COMBI]
                mer_sel = st.multiselect("Mercados (ajusta si el OCR falló)", list(MERCADOS_COMBI), default=pre, key="ms_" + local[0] + visita[0] + "_" + "_".join(pre))
                cuota = st.number_input("Cuota combinada de Betano (0 = no la tengo)", 0.0, 10000.0, 0.0, step=0.05, key="cap_cuota")
                if st.button("Calcular combinada", type="primary", key="cap_calc") and mer_sel:
                    conn = connect(CFG.db_path)
                    a = analizar_1x2(conn, CFG.data_dir, EQUIPOS[loc], EQUIPOS[vis])
                    conn.close()
                    if a is None:
                        st.error("Sin datos para ese partido.")
                    else:
                        corr, naive = _prob_partido_combi(a, [MERCADOS_COMBI[m] for m in mer_sel])
                        st.markdown("**Desglose: cómo baja con cada selección**")
                        st.table(_desglose([(m, _prob_individual(a, MERCADOS_COMBI[m])) for m in mer_sel]))
                        m1, m2 = st.columns(2)
                        m1.metric("Probabilidad de la combinada", _pct(corr), f"naive: {_pct(naive)}")
                        m2.metric("Cuota justa del modelo", f"{1 / corr:.2f}" if corr > 0 else "—")
                        if cuota and cuota > 1:
                            st.metric("Valor (EV)", f"{ev(corr, cuota):+.3f}" if a.fiable else "n/f")
                        st.info(f"**Por qué parece bajo:** la combinada se cumple solo si ocurren **las {len(mer_sel)} selecciones a la vez**, así que sus probabilidades se multiplican. Cada pata añadida baja la probabilidad total y sube la cuota. Tiene valor solo si tu cuota supera la justa del modelo.")

    st.divider()
    st.header("Analizar combinada")
    st.caption("Pega (Ctrl+V) o sube una o varias capturas de una combinada con partidos distintos. El bot detecta cada partido con su mercado; revísalo y corrige en la tabla antes de calcular.")
    from streamlit_paste_button import paste_image_button
    pegar_m = paste_image_button("📋 Pegar captura (Ctrl+V)", errors="ignore", key="multi_paste")
    multi = st.file_uploader("…o sube el/los archivo(s) (PNG/JPG)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="multi_up")
    imagenes = []
    if pegar_m.image_data is not None:
        import io as _io2
        _b = _io2.BytesIO()
        pegar_m.image_data.save(_b, format="PNG")
        imagenes.append(("(pegada)", _b.getvalue()))
    for f in multi or []:
        imagenes.append((f.name, f.getvalue()))
    if imagenes:
        import importlib

        import src.lector as _lm
        importlib.reload(_lm)
        eqs = equipos_busqueda()
        detectadas, textos = [], []
        for nombre, datos in imagenes:
            try:
                with st.spinner(f"Leyendo {nombre}..."):
                    txt = _lm.ocr(datos)
            except Exception as exc:
                st.error(f"No se pudo leer {nombre}: {exc}")
                continue
            textos.append(txt)
            detectadas.extend(_lm.analizar_multi(txt, eqs))
        with st.expander("Texto leído por el OCR (revisa si algo se detectó mal)"):
            for txt in textos:
                st.text(txt)
        if any("anotar en cualquier" in t.lower() or "marcar en cualquier" in t.lower() for t in textos):
            st.warning("Detecté mercado(s) de **goleador** (p. ej. *Anotar en cualquier momento*). El modelo Dixon-Coles no estima goles por jugador, así que **no se incluyen** en el cálculo: valóralos aparte.")
        cuota_detectada = next((c for c in (_lm.cuota_total(t) for t in textos) if c), 0.0) or 0.0
        vistas, filas_init = set(), []
        for loc, vis, m, cu in detectadas:
            clave = (loc[0], vis[0], m)
            if clave not in vistas:
                vistas.add(clave)
                filas_init.append({
                    "Local": next((n for n in NOMBRES if EQUIPOS[n] == loc[0]), NOMBRES[0]),
                    "Visitante": next((n for n in NOMBRES if EQUIPOS[n] == vis[0]), NOMBRES[1]),
                    "Mercado": m,
                    "Cuota Betano": float(cu) if cu else 0.0,
                })
        if not filas_init:
            st.warning("No detecté partidos con claridad. Añade las filas a mano en la tabla de abajo.")
            filas_init = [{"Local": NOMBRES[0], "Visitante": NOMBRES[1], "Mercado": list(MERCADOS_COMBI)[0], "Cuota Betano": 0.0}]
        st.markdown("**Selecciones detectadas** — corrige equipos/mercados/cuota o añade filas (botón +):")
        editor = st.data_editor(
            pd.DataFrame(filas_init), num_rows="dynamic", hide_index=True, use_container_width=True, key="multi_editor",
            column_config={
                "Local": st.column_config.SelectboxColumn(options=NOMBRES, required=True),
                "Visitante": st.column_config.SelectboxColumn(options=NOMBRES, required=True),
                "Mercado": st.column_config.SelectboxColumn(options=list(MERCADOS_COMBI), required=True),
                "Cuota Betano": st.column_config.NumberColumn(format="%.2f", help="Cuota de Betano de la selección (o del Bet Builder). 0 = no la tengo."),
            },
        )
        cuota_x = st.number_input("Cuota TOTAL de la combinada en Betano (0 = no la tengo)", 0.0, 100000.0, float(cuota_detectada), step=0.05, key="multi_cuota")
        if st.button("Calcular combinada", type="primary", key="multi_calc"):
            grupos: dict = {}
            cuotas_item: dict = {}
            for _, fila in editor.iterrows():
                if fila["Local"] in EQUIPOS and fila["Visitante"] in EQUIPOS and fila["Mercado"] in MERCADOS_COMBI:
                    clave_p = (EQUIPOS[fila["Local"]], EQUIPOS[fila["Visitante"]])
                    grupos.setdefault(clave_p, []).append(fila["Mercado"])
                    cu = fila.get("Cuota Betano", 0) or 0
                    if cu > 1 and clave_p not in cuotas_item:
                        cuotas_item[clave_p] = float(cu)
            conn = connect(CFG.db_path)
            p_corr, fiable, filas_res, ok = 1.0, True, [], True
            for (l, v), mers in grupos.items():
                a = analizar_1x2(conn, CFG.data_dir, l, v)
                if a is None:
                    st.error(f"Sin datos para {l}-{v}.")
                    ok = False
                    break
                corr, _ = _prob_partido_combi(a, [MERCADOS_COMBI[m] for m in mers])
                p_corr *= corr
                fiable = fiable and a.fiable
                cu_item = cuotas_item.get((l, v))
                ev_item = ev(corr, cu_item) if (cu_item and a.fiable) else None
                filas_res.append({
                    "Partido": f"{a.nombre_local}-{a.nombre_visita}",
                    "Mercado(s)": ", ".join(mers),
                    "Prob. modelo": _pct(corr),
                    "Cuota Betano": f"{cu_item:.2f}" if cu_item else "—",
                    "Cuota justa": f"{1 / corr:.2f}" if corr > 0 else "—",
                    "EV": f"{ev_item:+.1%}" if ev_item is not None else ("n/f" if cu_item else "—"),
                })
            conn.close()
            if ok and filas_res:
                st.markdown("**Valor por selección (probabilidad del modelo vs cuota real de Betano)**")
                st.table(pd.DataFrame(filas_res))
                m1, m2, m3 = st.columns(3)
                m1.metric("Prob. de la combinada", _pct(p_corr))
                m2.metric("Cuota justa del modelo", f"{1 / p_corr:.2f}" if p_corr > 0 else "—")
                if cuota_x and cuota_x > 1:
                    m3.metric("EV de la combinada", f"{ev(p_corr, cuota_x):+.1%}" if fiable else "n/f")
                    st.caption(f"Betano paga **{cuota_x:.2f}** vs cuota justa **{1 / p_corr:.2f}**. " + ("Tiene valor si Betano paga más que la justa." if fiable else "Modelo poco fiable en algún partido: EV no válido."))
                buenas = [f for f in filas_res if f["EV"] not in ("—", "n/f") and not f["EV"].startswith("-")]
                if buenas:
                    st.success("✅ Selecciones con valor (EV+): " + " · ".join(f"{f['Partido']} {f['Mercado(s)']} ({f['EV']})" for f in buenas))

    st.divider()
    with st.expander("✍️ Armar la combinada manualmente (incluye varios partidos)"):
        n = st.number_input("¿Cuántas selecciones?", 1, 8, 2, key="man_n")
        seleccion = []
        for i in range(int(n)):
            st.markdown(f"**Selección {i + 1}**")
            a1, a2, a3 = st.columns([1, 1, 1.4])
            loc = a1.selectbox("Local", NOMBRES, index=0, key=f"l{i}")
            vis = a2.selectbox("Visitante", NOMBRES, index=1, key=f"v{i}")
            mer = a3.selectbox("Mercado", list(MERCADOS_COMBI), key=f"m{i}")
            seleccion.append((EQUIPOS[loc], EQUIPOS[vis], mer))
        cuota_m = st.number_input("Cuota combinada de Betano (0 = no la tengo)", 0.0, 10000.0, 0.0, step=0.05, key="man_cuota")
        if st.button("Calcular", type="primary", key="man_calc"):
            grupos: dict = {}
            for l, v, mer in seleccion:
                grupos.setdefault((l, v), []).append(mer)
            conn = connect(CFG.db_path)
            p_corr, p_naive, fiable, pares, ok = 1.0, 1.0, True, [], True
            for (l, v), nombres in grupos.items():
                a = analizar_1x2(conn, CFG.data_dir, l, v)
                if a is None:
                    st.error(f"Sin datos para {l}-{v}.")
                    ok = False
                    break
                corr, naive = _prob_partido_combi(a, [MERCADOS_COMBI[nm] for nm in nombres])
                p_corr *= corr
                p_naive *= naive
                fiable = fiable and a.fiable
                for nm in nombres:
                    pares.append((f"{l}-{v}: {nm}", _prob_individual(a, MERCADOS_COMBI[nm])))
            conn.close()
            if ok:
                st.markdown("**Desglose: cómo baja con cada selección**")
                st.table(_desglose(pares))
                m1, m2 = st.columns(2)
                m1.metric("Probabilidad combinada (correcta)", _pct(p_corr), f"naive: {_pct(p_naive)}")
                if cuota_m and cuota_m > 1:
                    m2.metric("Valor (EV)", f"{ev(p_corr, cuota_m):+.3f}" if fiable else "n/f")
                    st.caption(f"Cuota justa según el modelo: **{1 / p_corr:.2f}**. " + ("Tiene valor solo si tu cuota la supera." if fiable else "Algún partido es poco fiable vs el mercado (EV no válido)."))

elif pagina == "Armar Bet Builder":
    st.title("Armar Bet Builder (Boost)")
    st.caption("Arma una combinada que cumpla el BB Boost de Betano: ≥3 mercados, cada cuota > 1.50, total > 5.00 (+25% de ganancias). "
               "Criterio: la combinación más probable que cumpla. Solo con partidos de hoy y mañana.")
    st.info("Las cuotas son la **cuota justa del modelo** (1÷probabilidad), no las exactas de Betano. **Verifica en Betano** que cada mercado supere 1.50 y el total 5.00 antes de apostar. No incluye mercados de goleador (el modelo no los calcula).")
    modo = st.radio("Combinar", ["Varios partidos (diversificado)", "Un solo partido (boost mismo evento)"], horizontal=True)
    cc1, cc2, cc3 = st.columns(3)
    cuota_min = cc1.number_input("Cuota mín. por mercado", 1.1, 5.0, 1.50, step=0.05)
    total_min = cc2.number_input("Cuota total mín.", 2.0, 50.0, 5.0, step=0.5)
    n_min = int(cc3.number_input("Mín. de mercados", 2, 13, 3))

    prox = proximos_partidos()
    idx_partido = None
    if prox and modo.startswith("Un solo"):
        opc = [f"{('Hoy' if p['dia'] == 0 else 'Mañana')} {p['hora']} · {p['ln']} vs {p['vn']}" for p in prox]
        idx_partido = st.selectbox("Partido", range(len(opc)), format_func=lambda i: opc[i])

    if not prox:
        st.warning("No hay partidos de hoy/mañana en la base. Corre `python -m scripts.actualizar` y reinicia.")
    elif st.button("Armar Bet Builder", type="primary"):
        with st.spinner("Analizando partidos..."):
            if modo.startswith("Un solo"):
                p = prox[idx_partido]
                conn = connect(CFG.db_path)
                a = analizar_1x2(conn, CFG.data_dir, p["lf"], p["vf"])
                conn.close()
                if a is None:
                    st.session_state.bb_result = None
                    st.error("Sin datos para ese partido.")
                else:
                    filas, prob, cuota, n, fiable = _armar_bb_partido(a, cuota_min, total_min, n_min)
                    st.session_state.bb_result = {"filas": filas, "prob": prob, "cuota": cuota, "n": n, "fiable": fiable,
                                                  "cumple": n >= n_min and cuota > total_min, "varios": False}
            else:
                filas, prob, cuota, n, fiable = _armar_bb_varios(prox, cuota_min, total_min, n_min)
                st.session_state.bb_result = {"filas": filas, "prob": prob, "cuota": cuota, "n": n, "fiable": fiable,
                                              "cumple": n >= n_min and cuota > total_min, "varios": True}

    r = st.session_state.get("bb_result")
    if r:
        if not r["filas"]:
            st.warning("No encontré mercados que cumplan (cuota > 1.50). Prueba bajar la cuota mínima.")
        else:
            if not r["cumple"]:
                st.warning(f"No llegué al mínimo (≥{n_min} mercados y total > {total_min}). Esto es lo más cercano; baja el total mínimo o usa 'varios partidos'.")
            st.table(pd.DataFrame(r["filas"]))
            m1, m2, m3 = st.columns(3)
            m1.metric("Mercados", r["n"])
            m2.metric("Cuota total (justa)", f"{r['cuota']:.2f}")
            m3.metric("Prob. de acertar", _pct(r["prob"]))
            stake = st.number_input("Stake para ver la ganancia (COP)", 0.0, 1e8, 10000.0, step=1000.0, key="bb_stake")
            if stake > 0 and r["cuota"] > 1:
                gan = stake * (r["cuota"] - 1)
                st.metric("Ganancia con BB Boost +25%", f"${gan * 1.25:,.0f}", f"sin boost: ${gan:,.0f}")
            if not r["fiable"]:
                st.caption("⚠ Algún partido diverge mucho del mercado (modelo poco fiable ahí); tómalo con cautela.")
            if r["varios"]:
                st.caption("Combina varios partidos: el boost del 25% de Betano normalmente aplica solo a Bet Builders de un **mismo evento**. Esta combinada quizá no califique para el boost (sí es una combinada válida). Para el boost, usa 'Un solo partido'.")

elif pagina == "Glosario":
    st.title("Qué significa cada término")
    st.markdown(
        """
- **Elo** — fuerza de una selección según sus resultados. 2000+ elite, ~1800 buena, ~1500 floja.
- **xG / xGA** — goles esperados que **genera** / **concede** por partido (calidad de ocasiones). Menos xGA = mejor defensa.
- **Valor plantilla** — valor de mercado de los jugadores (Transfermarkt); aproxima la calidad del plantel.
- **Modelo / Mercado / Apostar** — probabilidad del bot / de la cuota de Pinnacle sin margen / mezcla de ambas (la que se usa para el EV).
- **EV (valor esperado)** — cuánto ganas/pierdes de media por unidad apostada. **+** = hay valor; **−** = la cuota paga poco; **n/f** = el modelo no es fiable ahí (no apostar).
- **Over (+)** — "más de": +9.5 córners = 10 o más; +2.5 goles = 3 o más. El % es la probabilidad.
- **Ambos anotan (BTTS)** — que los dos equipos marquen al menos un gol.
- **CLV** — ¿tu cuota fue mejor que la de cierre del mercado? Si es positivo con el tiempo, vas bien.
        """
    )
