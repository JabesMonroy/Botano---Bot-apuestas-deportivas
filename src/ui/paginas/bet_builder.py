from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import Config
from src.db.database import connect
from src.reporte import analizar_club
from src.ui import datos, selector_liga
from src.ui.formato import pct
from src.ui.mercados import armar_bb_partido, armar_bb_varios


def render(cfg: Config) -> None:
    ligas = datos.cargar_ligas(cfg)
    if not ligas:
        st.warning("No hay competiciones cargadas. Corre `python -m scripts.cargar_mapeo_clubes`.", icon=":material/warning:")
        return
    proximo = datos.proximo_por_liga(cfg)
    ligas_ordenadas = sorted(ligas, key=lambda l: proximo.get(l["id"], {}).get("dias", 9999))

    st.title("Armar Bet Builder (Boost)")
    liga = selector_liga.selector_competicion(cfg, ligas_ordenadas, proximo, key="liga_global")
    st.caption("Arma una combinada que cumpla el BB Boost de Betano: ≥3 mercados, cada cuota > 1.50, total > 5.00 (+25% de ganancias). "
               "Criterio: la combinación más probable que cumpla. Solo con los próximos partidos de esta competición.")
    st.info("Las cuotas son la **cuota justa del modelo** (1÷probabilidad), no las exactas de Betano. **Verifica en Betano** que cada mercado supere 1.50 y el total 5.00 antes de apostar. No incluye mercados de goleador (el modelo no los calcula).", icon=":material/info:")
    modo = st.radio("Combinar", ["Varios partidos (diversificado)", "Un solo partido (boost mismo evento)"], horizontal=True)
    cc1, cc2, cc3 = st.columns(3)
    cuota_min = cc1.number_input("Cuota mín. por mercado", 1.1, 5.0, 1.50, step=0.05)
    total_min = cc2.number_input("Cuota total mín.", 2.0, 50.0, 5.0, step=0.5)
    n_min = int(cc3.number_input("Mín. de mercados", 2, 13, 3))

    prox = datos.proximos_partidos(cfg, dias=10, liga_id=liga["id"])
    idx_partido = None
    if prox and modo.startswith("Un solo"):
        opc = [f"{('Hoy' if p['dia'] == 0 else 'Mañana')} {p['hora']} · {p['ln']} vs {p['vn']}" for p in prox]
        idx_partido = st.selectbox("Partido", range(len(opc)), format_func=lambda i: opc[i])

    if not prox:
        st.warning("No hay próximos partidos de esta competición en la base. Pulsa **Refrescar datos** en la barra lateral.", icon=":material/warning:")
    elif st.button("Armar Bet Builder", type="primary", icon=":material/calculate:"):
        with st.spinner("Analizando partidos..."):
            if modo.startswith("Un solo"):
                p = prox[idx_partido]
                conn = connect(cfg.db_path)
                a = analizar_club(conn, cfg.data_dir, liga["codigo"], p["lf"], p["vf"])
                conn.close()
                if a is None:
                    st.session_state.bb_result = None
                    st.error("Sin datos para ese partido.", icon=":material/error:")
                else:
                    filas, prob, cuota, n, fiable = armar_bb_partido(a, cuota_min, total_min, n_min)
                    st.session_state.bb_result = {"filas": filas, "prob": prob, "cuota": cuota, "n": n, "fiable": fiable,
                                                  "cumple": n >= n_min and cuota > total_min, "varios": False}
            else:
                filas, prob, cuota, n, fiable = armar_bb_varios(cfg, liga["codigo"], prox, cuota_min, total_min, n_min)
                st.session_state.bb_result = {"filas": filas, "prob": prob, "cuota": cuota, "n": n, "fiable": fiable,
                                              "cumple": n >= n_min and cuota > total_min, "varios": True}

    r = st.session_state.get("bb_result")
    if r:
        if not r["filas"]:
            st.warning("No encontré mercados que cumplan (cuota > 1.50). Prueba bajar la cuota mínima.", icon=":material/warning:")
        else:
            if not r["cumple"]:
                st.warning(f"No llegué al mínimo (≥{n_min} mercados y total > {total_min}). Esto es lo más cercano; baja el total mínimo o usa 'varios partidos'.", icon=":material/warning:")
            st.dataframe(pd.DataFrame(r["filas"]), hide_index=True, width="stretch")
            m1, m2, m3 = st.columns(3)
            m1.metric("Mercados", r["n"])
            m2.metric("Cuota total (justa)", f"{r['cuota']:.2f}")
            m3.metric("Prob. de acertar", pct(r["prob"]))
            stake = st.number_input("Stake para ver la ganancia (COP)", 0.0, 1e8, 10000.0, step=1000.0, key="bb_stake")
            if stake > 0 and r["cuota"] > 1:
                gan = stake * (r["cuota"] - 1)
                st.metric("Ganancia con BB Boost +25%", f"${gan * 1.25:,.0f}", f"sin boost: ${gan:,.0f}")
            if not r["fiable"]:
                st.caption(":material/warning: Algún partido diverge mucho del mercado (modelo poco fiable ahí); tómalo con cautela.")
            if r["varios"]:
                st.caption("Combina varios partidos: el boost del 25% de Betano normalmente aplica solo a Bet Builders de un **mismo evento**. Esta combinada quizá no califique para el boost (sí es una combinada válida). Para el boost, usa 'Un solo partido'.")
