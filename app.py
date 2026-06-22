from __future__ import annotations

import pandas as pd
import streamlit as st

from src.apuestas import actualizar, registrar
from src.config import load_config
from src.db.database import connect
from src.modelo.bet_builder import prob_conjunta, prob_marginal
from src.modelo.dixon_coles import Ajustes
from src.modelo.secundarios import over_under
from src.modelo.valor import ev
from src.plantillas import detectar_ausencias, multiplicadores
from src.reporte import analizar_1x2, contexto_partido, nivel_confianza

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
MERCADOS = {
    "Gana local": "1", "Empate": "X", "Gana visita": "2",
    "Más de 2.5 goles": "over2.5", "Menos de 2.5 goles": "under2.5",
    "Ambos anotan": "btts", "No ambos anotan": "nobtts",
}


def _pct(x) -> str:
    return f"{x * 100:.1f}%" if x is not None else "—"


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


def mostrar_analisis(a, ctx) -> None:
    st.subheader(f"{a.nombre_local}  vs  {a.nombre_visita}")
    if ctx:
        fecha = ctx["fecha"][:16].replace("T", " ") if ctx["fecha"] else "?"
        st.caption(f"Grupo {ctx['grupo']} · {fecha} · {ctx['estado']}")

    izq, der = st.columns(2)
    pl, pv = a.perfil_local, a.perfil_visita

    def _xg(p):
        return f"{p['xg_fs']:.2f} / {p['xga_fs']:.2f}" if p.get("xg_fs") and p.get("xga_fs") else "—"

    perfil = pd.DataFrame(
        {
            a.nombre_local: [pl.get("elo"), pl.get("valor_plantilla"), _xg(pl), pl.get("corners_favor"), pl.get("tarjetas_partido")],
            a.nombre_visita: [pv.get("elo"), pv.get("valor_plantilla"), _xg(pv), pv.get("corners_favor"), pv.get("tarjetas_partido")],
        },
        index=["Elo", "Valor plantilla (M€)", "xG / xGA", "Córners (prom.)", "Tarjetas (prom.)"],
    )
    izq.markdown("**Perfil de los equipos**")
    izq.table(perfil)

    if ctx and ctx.get("standings"):
        der.markdown(f"**Grupo {ctx['grupo']}**")
        der.dataframe(
            pd.DataFrame([{"Pos": s["posicion"], "Equipo": s["nombre"], "PJ": s["jugados"], "Pts": s["puntos"], "DG": s["diferencia"]} for s in ctx["standings"]]),
            hide_index=True, use_container_width=True,
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
    if a.novig and not a.fiable:
        st.warning(f"El modelo difiere {a.divergencia * 100:.0f}pp del mercado: poco fiable, no apostar por esa diferencia.")

    g1, g2, g3 = st.columns(3)
    g1.metric("Goles esperados", f"{a.lh + a.la:.1f}")
    g1.caption(f"{a.nombre_local} {a.lh:.1f} - {a.la:.1f} {a.nombre_visita}")
    g2.metric("Over 2.5 goles", _pct(a.prob["over25"]))
    g3.metric("Ambos anotan", _pct(a.prob["btts_si"]))

    if a.corners_esp or a.tarjetas_esp:
        s1, s2 = st.columns(2)
        if a.corners_esp:
            o = over_under(a.corners_esp, [8.5, 9.5, 10.5])
            s1.metric("Córners esperados", f"{a.corners_esp:.1f}")
            s1.caption(" · ".join(f"+{l}: {_pct(p)}" for l, p in o.items()))
        if a.tarjetas_esp:
            o = over_under(a.tarjetas_esp, [2.5, 3.5, 4.5])
            s2.metric("Tarjetas esperadas", f"{a.tarjetas_esp:.1f}")
            s2.caption(" · ".join(f"+{l}: {_pct(p)}" for l, p in o.items()))

    st.info(f"Confianza del análisis: **{nivel_confianza(a)}**")


@st.cache_data(show_spinner=False)
def simular_cached(n: int):
    from src.modelo.torneo import cargar_estado, simular
    conn = connect(CFG.db_path)
    estado = cargar_estado(conn, CFG.data_dir)
    fifa = {api: r["fifa_code"] for api, r in estado[0].items()}
    conn.close()
    res = simular(estado, n)
    filas = [
        {"Equipo": fifa[api], "Avanza %": res["avanza"].get(api, 0) / n * 100, "Final %": res["finalista"].get(api, 0) / n * 100, "Campeón %": c / n * 100}
        for api, c in sorted(res["campeon"].items(), key=lambda x: -x[1])
    ]
    return pd.DataFrame(filas)


st.sidebar.title("⚽ Botano")
st.sidebar.caption("Mundial 2026")
pagina = st.sidebar.radio("Menú", ["Analizar partido", "Combinada", "Simular torneo", "Mis apuestas / CLV", "Glosario"])
st.sidebar.caption("Herramienta de análisis, no garantía de ganancia.")


if pagina == "Analizar partido":
    st.title("Analizar partido")
    c1, c2 = st.columns(2)
    local = c1.selectbox("Local", NOMBRES, index=0)
    visita = c2.selectbox("Visitante", NOMBRES, index=1)
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

elif pagina == "Combinada":
    st.title("Combinada (bet builder)")
    st.caption("Calcula la probabilidad real teniendo en cuenta la correlación entre selecciones del mismo partido.")
    n = st.number_input("¿Cuántas selecciones?", 1, 6, 2)
    seleccion = []
    for i in range(int(n)):
        st.markdown(f"**Selección {i + 1}**")
        a1, a2, a3 = st.columns(3)
        loc = a1.selectbox("Local", NOMBRES, index=0, key=f"l{i}")
        vis = a2.selectbox("Visitante", NOMBRES, index=1, key=f"v{i}")
        mer = a3.selectbox("Mercado", list(MERCADOS), key=f"m{i}")
        seleccion.append((EQUIPOS[loc], EQUIPOS[vis], MERCADOS[mer]))
    cuota = st.number_input("Cuota combinada de Betano (0 = no la tengo)", 0.0, 10000.0, 0.0, step=0.05)
    if st.button("Calcular", type="primary"):
        grupos: dict = {}
        for l, v, m in seleccion:
            grupos.setdefault((l, v), []).append(m)
        conn = connect(CFG.db_path)
        p_corr, p_naive, fiable, filas, ok = 1.0, 1.0, True, [], True
        for (l, v), mercados in grupos.items():
            a = analizar_1x2(conn, CFG.data_dir, l, v)
            if a is None:
                st.error(f"Sin datos para {l}-{v}.")
                ok = False
                break
            marg = {m: prob_marginal(a.matriz, m) for m in mercados}
            conj = prob_conjunta(a.matriz, mercados)
            naive = 1.0
            for m in mercados:
                naive *= marg[m]
            p_corr *= conj
            p_naive *= naive
            fiable = fiable and a.fiable
            filas.append({"Partido": f"{a.nombre_local}-{a.nombre_visita}", "Mercados": ", ".join(mercados), "Correcta": _pct(conj), "Naive": _pct(naive)})
        conn.close()
        if ok:
            st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
            m1, m2 = st.columns(2)
            m1.metric("Probabilidad combinada (correcta)", _pct(p_corr), f"naive: {_pct(p_naive)}")
            if cuota and cuota > 1:
                m2.metric("Valor (EV)", f"{ev(p_corr, cuota):+.3f}" if fiable else "n/f")

elif pagina == "Simular torneo":
    st.title("Simulación del torneo")
    st.caption("Probabilidad de avanzar y de ser campeón. P(avanza) es robusta; P(campeón) tiende a sobrevalorar (ver glosario).")
    n = st.select_slider("Iteraciones", [2000, 5000, 10000, 20000], value=10000)
    if st.button("Simular", type="primary"):
        with st.spinner("Simulando el torneo..."):
            df = simular_cached(int(n))
        st.bar_chart(df.head(12).set_index("Equipo")["Campeón %"])
        st.dataframe(
            df.style.format({"Avanza %": "{:.1f}", "Final %": "{:.1f}", "Campeón %": "{:.1f}"}),
            hide_index=True, use_container_width=True,
        )

elif pagina == "Mis apuestas / CLV":
    st.title("Mis apuestas y CLV")
    with st.form("registrar"):
        st.markdown("**Registrar una apuesta hecha en Betano**")
        b1, b2, b3 = st.columns(3)
        loc = b1.selectbox("Local", NOMBRES, index=0)
        vis = b2.selectbox("Visitante", NOMBRES, index=1)
        sel = b3.selectbox("Tu apuesta", ["Gana local (1)", "Empate (X)", "Gana visita (2)"])
        b4, b5 = st.columns(2)
        cuota = b4.number_input("Cuota de Betano", 1.01, 1000.0, 2.0, step=0.05)
        stake = b5.number_input("Stake (0 = sugerencia Kelly)", 0.0, 100000.0, 0.0)
        if st.form_submit_button("Registrar", type="primary"):
            conn = connect(CFG.db_path)
            mapa = {"Gana local (1)": "1", "Empate (X)": "X", "Gana visita (2)": "2"}
            r = registrar(conn, CFG.data_dir, EQUIPOS[loc], EQUIPOS[vis], mapa[sel], cuota, stake if stake > 0 else None)
            conn.close()
            if r:
                st.success(f"Registrada. EV {r['ev']:+.3f} · Kelly sugerido {r['kelly_pct']:.1f}% del bankroll")
            else:
                st.error("No se pudo registrar (revisa el partido).")

    conn = connect(CFG.db_path)
    actualizar(conn)
    rows = conn.execute(
        "SELECT a.seleccion, a.cuota_betano, a.cuota_cierre, a.clv, a.ev, a.stake, a.resultado, el.fifa_code fl, ev.fifa_code fv "
        "FROM apuestas a JOIN partidos p ON a.partido_id=p.id JOIN equipos el ON p.equipo_local_id=el.id "
        "JOIN equipos ev ON p.equipo_visita_id=ev.id ORDER BY a.fecha"
    ).fetchall()
    conn.close()
    if rows:
        df = pd.DataFrame([
            {"Partido": f"{r['fl']}-{r['fv']}", "Apuesta": r["seleccion"], "Cuota": r["cuota_betano"], "Cierre": r["cuota_cierre"],
             "CLV": (f"{r['clv'] * 100:+.1f}%" if r["clv"] is not None else "—"), "EV": f"{r['ev']:+.3f}", "Stake": r["stake"], "Resultado": r["resultado"] or "pendiente"}
            for r in rows
        ])
        st.dataframe(df, hide_index=True, use_container_width=True)
        clvs = [r["clv"] for r in rows if r["clv"] is not None]
        if clvs:
            st.metric("CLV medio", f"{sum(clvs) / len(clvs) * 100:+.2f}%", f"{sum(1 for c in clvs if c > 0)}/{len(clvs)} positivos")
    else:
        st.caption("Aún no has registrado apuestas.")

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
