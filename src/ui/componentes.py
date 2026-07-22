from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

from src.config import Config
from src.modelo.secundarios import over_under, over_under_nb
from src.modelo.valor import ev
from src.reporte import narrativa, nivel_confianza
from src.ui import mercados_cupon
from src.ui.datos import info_equipo, params_tiros, tasa_arbitro
from src.ui.formato import corners_equipo, dist_goles, estilo_texto, over_equipo, pct, primer_gol
from src.ui.mercados import parley_sugerido, prob_partido_combi, MERCADOS_COMBI

FASES_ELIMINACION = {"LAST_32", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "THIRD_PLACE", "FINAL"}
_MERCADO_BD = {"1x2": "1X2", "goles_totales": "totals"}


def _panel_agregar_cupon(cfg: Config, a, tarjetas_final: float | None) -> None:
    if "cupon" not in st.session_state:
        st.session_state.cupon = []
    clave = f"cupon_{a.local}_{a.visita}"
    opciones = mercados_cupon.mercados_disponibles(a)
    etiquetas_m = dict(opciones)

    with st.container(border=True):
        st.markdown("**:material/receipt_long: Agregar esta apuesta al cupón**")
        c1, c2 = st.columns([2, 1.3])
        mercado = c1.selectbox(
            "Mercado", [m for m, _ in opciones], format_func=lambda m: etiquetas_m[m], key=f"{clave}_mercado"
        )
        lados = mercados_cupon.lados_fijos(mercado, a)
        if lados:
            etq_lado = dict(lados)
            lado = c2.selectbox("Selección", [l for l, _ in lados], format_func=lambda l: etq_lado[l], key=f"{clave}_lado_{mercado}")
            linea = None
            etiqueta_sel = etq_lado[lado]
        else:
            linea_default = float(mercados_cupon.LINEA_SUGERIDA.get(mercado, 0.5))
            lc1, lc2 = c2.columns(2)
            linea = lc1.number_input("Línea", min_value=0.5, value=linea_default, step=1.0, key=f"{clave}_linea_{mercado}", label_visibility="collapsed")
            lado = lc2.selectbox("Lado", ["over", "under"], format_func=lambda x: "Más de" if x == "over" else "Menos de", key=f"{clave}_ou_{mercado}", label_visibility="collapsed")
            etiqueta_sel = mercados_cupon.etiqueta_over_under(mercado, a, linea, lado)

        prob = mercados_cupon.calcular_prob(cfg, a, tarjetas_final, mercado, lado, linea)

        c3, c4, c5 = st.columns(3)
        cuota = c3.number_input("Cuota Betano", 1.01, 1000.0, 1.50, step=0.01, key=f"{clave}_cuota")
        stake = c4.number_input("Cuánto aposté (COP)", 0.0, 10_000_000.0, 10000.0, step=1000.0, format="%.0f", key=f"{clave}_stake_{mercado}")
        if prob is not None and prob > 0:
            c5.caption(f"Modelo: **{prob * 100:.1f}%** · cuota justa **{1 / prob:.2f}**")
        else:
            c5.caption("Sin datos suficientes para este mercado en este partido.")
        if st.button("Agregar al cupón", key=f"{clave}_btn_{mercado}", icon=":material/add_shopping_cart:", width="stretch", type="primary", disabled=not prob):
            st.session_state.cupon.append({
                "uid": uuid.uuid4().hex[:12],
                "local": a.local, "visita": a.visita,
                "nombre_local": a.nombre_local, "nombre_visita": a.nombre_visita,
                "mercado": _MERCADO_BD.get(mercado, mercado),
                "seleccion": lado if lados else f"{lado}{linea}",
                "etiqueta": etiqueta_sel, "prob_modelo": prob, "cuota_betano": cuota, "stake": stake,
            })
            st.toast(f"Agregado al cupón: {etiqueta_sel}", icon=":material/add_shopping_cart:")
        st.caption("Elige mercado y selección, pon la cuota y cuánto apostaste, y agrégala. Queda lista para registrar en **Mi cupón**, en la barra lateral.")
        if a.metodo == "clubes" and not (a.corners_esp and a.tarjetas_esp):
            faltan = [n for n, disp in (("córners", a.corners_esp), ("tarjetas", a.tarjetas_esp)) if not disp]
            st.caption(
                f":material/info: Esta liga no tiene {' ni '.join(faltan)} en el selector — football-data.co.uk no publica "
                "esas estadísticas por partido para esta competición (solo goles), no es un error del bot."
            )


def _chip_equipo(nombre: str, info: dict | None) -> str:
    color = (info or {}).get("color_principal") or "#888888"
    escudo = (info or {}).get("escudo_url")
    img_html = f'<img src="{escudo}" width="28" style="vertical-align:middle;margin-right:6px;border-radius:4px">' if escudo else ""
    return (
        '<span style="display:inline-flex;align-items:center;gap:6px;font-size:1.4rem;font-weight:600">'
        f"{img_html}"
        f'<span style="width:10px;height:10px;border-radius:50%;background:{color};display:inline-block;flex-shrink:0"></span>'
        f"{nombre}</span>"
    )


def _color_ev(col):
    estilos = []
    for x in col:
        if isinstance(x, str) and x.startswith("+"):
            estilos.append("color: #1e8449; font-weight: bold")
        elif isinstance(x, str) and x.startswith("-"):
            estilos.append("color: #c0392b")
        else:
            estilos.append("color: gray")
    return estilos


def mostrar_analisis(cfg: Config, a, ctx: dict | None) -> None:
    from scripts.predecir_ko import clasifica

    arb_stats = tasa_arbitro(cfg, ctx.get("arbitro")) if ctx and ctx.get("arbitro") else None
    tarjetas_final = a.tarjetas_esp
    if a.tarjetas_esp and arb_stats:
        tarjetas_final = 0.5 * a.tarjetas_esp + 0.5 * arb_stats["amarillas_pp"]

    club = a.metodo == "clubes"
    etiqueta_grupo = (ctx and ctx.get("liga_nombre")) or (ctx and f"Grupo {ctx['grupo']}") or ""

    info_l, info_v = info_equipo(cfg, a.local), info_equipo(cfg, a.visita)
    st.markdown(
        f"{_chip_equipo(a.nombre_local, info_l)}&nbsp;&nbsp;vs&nbsp;&nbsp;{_chip_equipo(a.nombre_visita, info_v)}",
        unsafe_allow_html=True,
    )
    if ctx:
        fecha = ctx["fecha"][:16].replace("T", " ") if ctx["fecha"] else "?"
        arb = ""
        if ctx.get("arbitro"):
            arb = f" · Árbitro: {ctx['arbitro']}"
            if arb_stats:
                arb += f" ({arb_stats['amarillas_pp']:.1f} amarillas/partido)"
        st.caption(f"{etiqueta_grupo} · {fecha} · {ctx['estado']}{arb}")

    _panel_agregar_cupon(cfg, a, tarjetas_final)

    izq, der = st.columns(2)
    pl, pv = a.perfil_local, a.perfil_visita

    def _xg(p):
        return f"{p['xg_fs']:.2f} / {p['xga_fs']:.2f}" if p.get("xg_fs") and p.get("xga_fs") else "—"

    if not club:
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
        der.markdown(f"**{etiqueta_grupo}**")
        der.dataframe(
            pd.DataFrame([{"Pos": s["posicion"], "Equipo": s["nombre"], "PJ": s["jugados"], "Pts": s["puntos"], "DG": s["diferencia"]} for s in ctx["standings"]]),
            hide_index=True, width="stretch",
        )
        der.caption("Resultados y tabla: football-data.org")

    if not club:
        st.caption(
            f"**Planteamiento esperado** (inferido del estilo de juego con datos reales, no declarado por el técnico): "
            f"{a.nombre_local} → _{estilo_texto(pl)}_  ·  {a.nombre_visita} → _{estilo_texto(pv)}_"
        )

    st.markdown("**Pronóstico (resultado del partido)**")
    clave = {"1": a.local, "X": "X", "2": a.visita}
    filas = []
    for sel, etq in (("1", f"Gana {a.nombre_local}"), ("X", "Empate"), ("2", f"Gana {a.nombre_visita}")):
        cu = a.cuotas.get(clave[sel])
        evtxt = (f"{ev(a.trabajo[sel], cu):+.3f}" if a.fiable else "n/f") if cu else "—"
        filas.append({
            "Resultado": etq, "Modelo": pct(a.modelo[sel]), "Mercado": pct(a.novig.get(sel)),
            "Apostar": pct(a.trabajo[sel]), "Cuota": f"{cu:.2f}" if cu else "—", "EV": evtxt,
        })

    st.dataframe(pd.DataFrame(filas).style.apply(_color_ev, subset=["EV"]), hide_index=True, width="stretch")
    st.caption(
        "**Cómo leer esto** · **Modelo**: probabilidad que estima el bot. "
        "**Mercado**: la misma probabilidad según la cuota de Pinnacle, quitándole el margen de la casa (fuente: The Odds API). "
        "**Apostar**: mezcla de las dos, es la que se usa para el valor. "
        "**EV (valor esperado)**: cuánto ganas/pierdes de media por cada €1 apostado a esa cuota — "
        ":green[:material/trending_up: positivo = hay valor] (candidato a apostar), "
        ":red[:material/trending_down: negativo] = la cuota paga menos de lo justo, "
        "**n/f** = el modelo no es fiable en este partido (no apostar)."
    )
    if a.novig and not a.fiable:
        st.warning(f"El modelo difiere {a.divergencia * 100:.0f}pp del mercado: poco fiable, no apostar por esa diferencia.", icon=":material/warning:")

    st.markdown("**Doble oportunidad** (se cubren dos de los tres resultados)")
    d1, d2, d3 = st.columns(3)
    d1.metric(f"{a.nombre_local} o empate", pct(a.modelo["1"] + a.modelo["X"]))
    d2.metric(f"Empate o {a.nombre_visita}", pct(a.modelo["X"] + a.modelo["2"]))
    d3.metric(f"{a.nombre_local} o {a.nombre_visita}", pct(a.modelo["1"] + a.modelo["2"]))
    st.caption("Sale de la **misma matriz Dixon-Coles** del modelo (no es una media): se suman las probabilidades de los dos resultados que cubre cada apuesta.")

    if ctx and ctx.get("fase") in FASES_ELIMINACION:
        av1, av2 = clasifica(a)
        favn, favp = (a.nombre_local, av1) if av1 >= av2 else (a.nombre_visita, av2)
        st.markdown("**Clasificación a la siguiente ronda** (incluye prórroga y penales)")
        q1, q2, q3 = st.columns(3)
        q1.metric(f"Clasifica {a.nombre_local}", pct(av1))
        q2.metric(f"Clasifica {a.nombre_visita}", pct(av2))
        q3.metric("Va a prórroga (empate 90')", pct(a.modelo["X"]))
        st.caption(
            f"Es eliminación directa: no hay empate final. **{favn} avanza con {pct(favp)}** (cuota justa {1 / favp:.2f}). "
            "Si hay empate a los 90', se juega la **prórroga con el mismo modelo a ritmo de 30 minutos** (λ÷3) y, "
            "si persiste el empate, los **penales se tratan como moneda al aire (50/50)** — así no se sobrevalora al favorito. "
            "Esto es el mercado **'Para avanzar/Clasificación'** de Betano (cuenta prórroga y penales), **no** el 1X2, "
            "que se liquida a los 90 minutos: si el partido acaba empatado en los 90', el 1X2 paga el empate aunque luego "
            "tu equipo quede fuera en penales."
        )

    st.markdown("#### Interpretación")
    st.markdown(narrativa(a))

    st.markdown("#### Goles")
    g1, g2, g3 = st.columns(3)
    g1.metric("Goles esperados", f"{a.lh + a.la:.1f}")
    g1.caption(f"{a.nombre_local} {a.lh:.1f} - {a.la:.1f} {a.nombre_visita}")
    g2.metric("Over 2.5 goles", pct(a.prob["over25"]))
    g3.metric("Ambos anotan", pct(a.prob["btts_si"]))
    st.caption("Calculado por el **modelo Dixon-Coles** del bot (no es un dato de fuente externa): estima los goles de cada equipo y de ahí la probabilidad de cada marcador.")

    if a.goles_mercado or a.btts_mercado:
        pares = []
        if a.goles_mercado:
            g = a.goles_mercado
            pares += [(f"Más de {g['linea']} goles", g, "over"), (f"Menos de {g['linea']} goles", g, "under")]
        if a.btts_mercado:
            pares += [("Ambos anotan: Sí", a.btts_mercado, "si"), ("Ambos anotan: No", a.btts_mercado, "no")]
        filas_gm = []
        for etq, g, lado in pares:
            cu = g["cuotas"][lado]
            filas_gm.append({
                "Selección": etq, "Modelo": pct(g["modelo"][lado]), "Mercado": pct(g["novig"][lado]),
                "Apostar": pct(g["trabajo"][lado]), "Cuota": f"{cu:.2f}",
                "EV": f"{g['ev'][lado]:+.3f}" if g["fiable"] else "n/f",
            })
        st.markdown("**Goles vs mercado (Pinnacle)**")
        st.dataframe(pd.DataFrame(filas_gm).style.apply(_color_ev, subset=["EV"]), hide_index=True, width="stretch")
        st.caption(
            "Misma lectura que el 1X2: *Mercado* es la cuota de Pinnacle sin margen, *Apostar* mezcla modelo y mercado "
            "(aquí con **más peso al mercado**, 80%, porque en goles el modelo no ha demostrado ventaja) y el **EV** compara con la cuota. "
            "En líneas asiáticas de cuarto (p. ej. 2.25) el EV ya descuenta las medias apuestas devueltas. "
            "**n/f** = divergencia excesiva, no apostar."
        )

    if a.corners_esp or a.tarjetas_esp or a.saques_local:
        st.markdown("#### Córners, tarjetas y saques de meta")
        s1, s2, s3 = st.columns(3)
        if a.corners_esp:
            o = over_under(a.corners_esp, [5.5, 8.5, 9.5, 10.5])
            s1.metric("Córners esperados", f"{a.corners_esp:.1f}")
            s1.caption(" · ".join(f"+{l}: {pct(p)}" for l, p in o.items()))
        if a.tarjetas_esp:
            o = over_under_nb(tarjetas_final, a.tarjetas_ratio_var, [2.5, 3.5, 4.5])
            s2.metric("Tarjetas esperadas", f"{tarjetas_final:.1f}", "ajustado por el árbitro" if arb_stats else None)
            s2.caption(" · ".join(f"+{l}: {pct(p)}" for l, p in o.items()))
        if a.saques_local and a.saques_visita:
            tot_sm = a.saques_local + a.saques_visita
            o = over_under(tot_sm, [13.5, 15.5, 17.5])
            s3.metric("Saques de meta esperados", f"{tot_sm:.1f}")
            s3.caption(" · ".join(f"+{l}: {pct(p)}" for l, p in o.items()))
        nota_arb = ", combinados con la **severidad del árbitro** (Transfermarkt)" if arb_stats else ""
        nota_wc = f" y con lo **observado en este Mundial** (eventos de wc2026-events/WhoScored, {a.n_wc} partidos por equipo)" if a.n_wc else ""
        st.caption(
            f"Córners y saques de meta: **Poisson** sobre promedios de cada selección (Footystats){nota_wc}. "
            f"Tarjetas: **binomial negativa** (recoge que unos partidos se calientan y otros no){nota_arb}. '+9.5' = 10 o más."
        )
    elif club:
        st.info(
            "Sin córners ni tarjetas para esta competición: la fuente histórica (football-data.co.uk) solo publica "
            "goles para esta liga, no estadísticas de partido. No es un fallo del bot — falta la fuente.",
            icon=":material/info:",
        )

    st.markdown("#### Tiros (estimación a partir del xG)")
    k, ratio_arco = params_tiros(cfg)
    tiros_l, tiros_v = a.lh / k, a.la / k
    arco_l, arco_v = tiros_l * ratio_arco, tiros_v * ratio_arco
    z1, z2, z3 = st.columns(3)
    z1.metric(f"Tiros {a.nombre_local}", f"{tiros_l:.0f}", f"al arco ~{arco_l:.0f}")
    z2.metric(f"Tiros {a.nombre_visita}", f"{tiros_v:.0f}", f"al arco ~{arco_v:.0f}")
    z3.metric("Tiros totales", f"{tiros_l + tiros_v:.0f}", f"al arco ~{arco_l + arco_v:.0f}")
    zt, za = st.columns(2)
    ot = over_under(tiros_l + tiros_v, [x + 0.5 for x in range(12, 25)])
    zt.markdown("**Tiros totales (líneas)**")
    zt.dataframe(pd.DataFrame([{"Línea": l, "Más de": pct(p), "Menos de": pct(1 - p)} for l, p in ot.items()]), hide_index=True, width="stretch")
    oa = over_under(arco_l + arco_v, [x + 0.5 for x in range(2, 9)])
    za.markdown("**Tiros al arco totales (líneas)**")
    za.dataframe(pd.DataFrame([{"Línea": l, "Más de": pct(p), "Menos de": pct(1 - p)} for l, p in oa.items()]), hide_index=True, width="stretch")
    st.info(f"**Estimación** (no es un dato medido): tiros ≈ goles esperados ÷ {k:.3f} y al arco ≈ {ratio_arco * 100:.0f}% — **parámetros calibrados con los tiros reales del Mundial 2022 (StatsBomb)**, no inventados. Orientativo.", icon=":material/info:")

    st.markdown("#### Probabilidades por línea (más de / menos de)")
    col_g, col_c, col_t = st.columns(3)
    dist = dist_goles(a.matriz)
    col_g.markdown("**Goles totales**")
    col_g.table(pd.DataFrame([
        {"Línea": x, "Más de": pct(float(dist[int(x) + 1:].sum())), "Menos de": pct(1 - float(dist[int(x) + 1:].sum()))}
        for x in (0.5, 1.5, 2.5, 3.5, 4.5)
    ]))
    col_g.caption(f"Debido a que se esperan **{a.lh + a.la:.1f} goles** (ataque de {a.nombre_local} vs defensa de {a.nombre_visita} y viceversa): las líneas bajas son casi seguras y las altas caen rápido.")
    if a.corners_esp:
        oc = over_under(a.corners_esp, [3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5])
        col_c.markdown("**Córners totales**")
        col_c.dataframe(pd.DataFrame([{"Línea": l, "Más de": pct(p), "Menos de": pct(1 - p)} for l, p in oc.items()]), hide_index=True, width="stretch")
        cl_esp, cv_esp = corners_equipo(cfg, a)
        if cl_esp is not None:
            col_c.markdown("**Córners por equipo** (reparto según el dominio)")
            filas_ce = []
            for nombre, esp in ((a.nombre_local, cl_esp), (a.nombre_visita, cv_esp)):
                oce = over_under(esp, [2.5, 3.5, 4.5, 5.5])
                fila = {"Equipo": nombre, "Esperados": f"{esp:.1f}"}
                fila.update({f"+{l}": pct(p) for l, p in oce.items()})
                filas_ce.append(fila)
            col_c.dataframe(pd.DataFrame(filas_ce), hide_index=True, width="stretch")
            col_c.caption(f"El **reparto** sí depende del dominio (corr 0.49 en datos de StatsBomb): {a.nombre_local} {cl_esp:.1f} vs {cv_esp:.1f} {a.nombre_visita}. El **total** es más ruidoso, por eso se mantiene en el promedio.")
    if a.tarjetas_esp:
        ot = over_under_nb(tarjetas_final, a.tarjetas_ratio_var, [0.5, 1.5, 2.5, 3.5, 4.5, 5.5])
        col_t.markdown("**Tarjetas totales**")
        col_t.table(pd.DataFrame([{"Línea": l, "Más de": pct(p), "Menos de": pct(1 - p)} for l, p in ot.items()]))
        razon = f"árbitro **{ctx['arbitro']}** ({arb_stats['amarillas_pp']:.1f}/partido)" if (arb_stats and ctx) else "la intensidad del partido"
        col_t.caption(f"Debido a **{tarjetas_final:.1f} tarjetas** esperadas, influidas por {razon}.")

    if a.saques_local and a.saques_visita:
        st.markdown("#### Saques de meta (más de / menos de)")
        sm1, sm2 = st.columns(2)
        tot_sm = a.saques_local + a.saques_visita
        osm = over_under(tot_sm, [12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5])
        sm1.markdown("**Totales del partido**")
        sm1.dataframe(pd.DataFrame([{"Línea": l, "Más de": pct(p), "Menos de": pct(1 - p)} for l, p in osm.items()]), hide_index=True, width="stretch")
        sm2.markdown("**Por equipo**")
        filas_sm = []
        for nombre, esp in ((a.nombre_local, a.saques_local), (a.nombre_visita, a.saques_visita)):
            oeq = over_under(esp, [5.5, 6.5, 7.5, 8.5])
            fila = {"Equipo": nombre, "Esperados": f"{esp:.1f}"}
            fila.update({f"+{l}": pct(p) for l, p in oeq.items()})
            filas_sm.append(fila)
        sm2.dataframe(pd.DataFrame(filas_sm), hide_index=True, width="stretch")
        sm2.caption(
            "Saque de meta: el balón sale por la línea de fondo tocado por el rival, sin gol ni córner. "
            "Un equipo que **recibe muchos tiros desviados** o despeja mucho tiende a más saques de meta. "
            "Promedios **reales de este Mundial** (wc2026-events), encogidos a la media del torneo según los partidos jugados."
        )

    st.markdown("#### Goles por equipo y primer gol")
    eq1, eq2, eq3 = st.columns(3)
    eq1.markdown(f"**{a.nombre_local} marca…**")
    eq1.table(pd.DataFrame([{"Goles": x, "Más de": pct(over_equipo(a.matriz, 0, x)), "Menos de": pct(1 - over_equipo(a.matriz, 0, x))} for x in (0.5, 1.5, 2.5, 3.5)]))
    eq2.markdown(f"**{a.nombre_visita} marca…**")
    eq2.table(pd.DataFrame([{"Goles": x, "Más de": pct(over_equipo(a.matriz, 1, x)), "Menos de": pct(1 - over_equipo(a.matriz, 1, x))} for x in (0.5, 1.5, 2.5, 3.5)]))
    p_local, p_visita, p_sin = primer_gol(a.lh, a.la, float(a.matriz[0, 0]))
    eq3.markdown("**¿Quién marca primero?**")
    eq3.metric(a.nombre_local, pct(p_local))
    eq3.metric(a.nombre_visita, pct(p_visita))
    eq3.caption(f"Ningún gol: {pct(p_sin)} · estimado por el ritmo goleador de cada equipo (modelo de Poisson en el tiempo).")

    tot = a.lh + a.la
    tend = "tiende a pocos goles" if tot < 2.3 else ("tiende a muchos goles" if tot > 2.9 else "tendencia media de goles")
    just = f"**Goles**: con {tot:.1f} esperados, el partido {tend}; por eso las líneas bajas son casi seguras y las altas caen rápido. "
    just += f"**Córners**: {a.nombre_local} es {estilo_texto(pl)} y {a.nombre_visita} es {estilo_texto(pv)} — cuanto más ofensivo y dominante, más córners. "
    if tarjetas_final is not None:
        just += f"**Tarjetas** (~{tarjetas_final:.1f} esperadas): suben con la intensidad y con el criterio del árbitro"
        if arb_stats:
            sev = "severo" if arb_stats["amarillas_pp"] >= 4.5 else ("permisivo" if arb_stats["amarillas_pp"] < 3.5 else "moderado")
            just += f" — **{ctx['arbitro']}** es {sev} ({arb_stats['amarillas_pp']:.1f} amarillas/partido), ya reflejado en la cifra."
        elif ctx and ctx.get("arbitro"):
            just += f" (designado: {ctx['arbitro']})."
        else:
            just += " (árbitro aún sin designar)."
    st.caption(just)

    st.info(f"Confianza del análisis: **{nivel_confianza(a)}**", icon=":material/verified:")

    parley = parley_sugerido(a)
    if parley:
        st.markdown("#### :material/track_changes: Parley sugerido (cada selección ≥ 68%)")
        st.table(pd.DataFrame([{"Selección": c, "Probabilidad": pct(p), "Cuota mínima p/ valor": f"{1 / p:.2f}"} for c, p in parley]))
        p_parley, p_naive_parley = prob_partido_combi(a, [MERCADOS_COMBI[c] for c, _ in parley])
        pm1, pm2 = st.columns(2)
        pm1.metric("Probabilidad del parley", pct(p_parley), f"sin correlación: {pct(p_naive_parley)}")
        pm2.metric("Cuota mínima del parley p/ valor", f"{1 / p_parley:.2f}" if p_parley > 0 else "—")
        st.caption(
            "Cada selección supera el 68% individualmente. La probabilidad del parley **no es** el producto de las patas: "
            "el modelo ajusta por la **correlación** entre los mercados de goles del mismo partido (por eso difiere del 'sin correlación'). "
            "La **cuota mínima** es la cuota justa (1÷probabilidad): si Betano paga **más**, hay valor. Es el mismo cálculo que en 'Analizar apuesta'."
        )

    with st.expander("¿De dónde salen estos números? (fuentes y modelos)"):
        st.markdown(
            """
**Fuentes de los datos**
- **Elo** de selecciones → eloratings.net
- **Valor de plantilla** → Transfermarkt
- **xG/xGA, córners, tarjetas** (previas al Mundial) → Footystats
- **Eventos reales del Mundial 2026** (tiros con xG propio, córners, tarjetas, saques de meta) → wc2026-events (WhoScored)
- **Cuotas y mercado** (Pinnacle) → The Odds API
- **Resultados y tabla del grupo** → football-data.org
- **Histórico de selección 2022-24** (para entrenar el modelo) → API-Football

**Modelos estadísticos**
- **Goles → Dixon-Coles** (Poisson bivariado con corrección de marcadores bajos): estima los goles esperados de cada equipo (λ) y construye la probabilidad de cada marcador. De esa matriz salen 1X2, Over/Under y Ambos anotan, todos coherentes entre sí (incluida la corrección de empate, aplicada a la matriz entera).
- **Fuerza de cada selección**: estimada de ~1.900 partidos (2022-26) con **ponderación temporal**, **anclada al Elo** y ajustada por el **valor de plantilla** (calibrado contra el mercado). Los partidos del Mundial entran con una **mezcla de xG y goles** (el xG tiene menos ruido con pocos partidos) y sin ventaja de local salvo los anfitriones. Un ajuste de nivel de torneo (*mu_torneo*) corrige que este Mundial va con más goles que el histórico.
- **Mercado y valor**: la columna *Mercado* quita el margen de la casa a la cuota de Pinnacle con el método *power* (corrige el sesgo favorito-longshot); *Apostar* mezcla modelo y mercado (*shrinkage*, más peso al mercado en partidos reñidos); el **EV** compara esa probabilidad con la cuota. Un **guardarraíl** marca "n/f" cuando el modelo se aleja demasiado del mercado.
- **Eliminatorias**: si hay empate a los 90' se modela la **prórroga** (mismo modelo a λ÷3) y los **penales al 50/50**.
- **Córners y saques de meta → Poisson**; **tarjetas → binomial negativa** (sobredispersión); promedios de Footystats mezclados con lo observado en este Mundial.
            """
        )
