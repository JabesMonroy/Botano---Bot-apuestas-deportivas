from __future__ import annotations

import json
import os

import streamlit as st

from src.config import load_config
from src.ui import cupon, datos
from src.ui.paginas import analizar_apuesta, analizar_partido, bet_builder, fiabilidad, glosario, mis_apuestas

st.set_page_config(page_title="Botano", page_icon=":material/sports_soccer:", layout="wide", initial_sidebar_state="auto")

st.markdown(
    """
    <style>
    @media (max-width: 640px) {
        .block-container { padding: 2.6rem 0.7rem 1rem 0.7rem; }
        h1 { font-size: 1.6rem; }
        h2 { font-size: 1.3rem; }
        [data-testid="stMetricValue"] { font-size: 1.2rem; }
    }
    [data-testid="stDataFrame"] { width: 100%; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _plain(v):
    if hasattr(v, "items"):
        return {k: _plain(x) for k, x in v.items()}
    return v


try:
    _secrets = dict(st.secrets)
except Exception:
    _secrets = {}
for _k, _val in _secrets.items():
    os.environ[_k] = _val if isinstance(_val, str) else json.dumps(_plain(_val))

CFG = load_config()


def _refrescar_datos() -> None:
    with st.sidebar, st.spinner("Actualizando ligas..."):
        try:
            r = datos.actualizar_datos(CFG)
        except Exception as exc:
            st.error(f"No se pudo refrescar: {exc}", icon=":material/error:")
            return
    st.cache_data.clear()
    total_partidos = sum(rl.get("partidos", 0) for rl in r["ligas"].values())
    total_cuotas = sum(rl.get("cuotas", {}).get("1x2", 0) for rl in r["ligas"].values())
    st.toast(
        f"Actualizado: {total_partidos} partidos en {len(r['ligas'])} competiciones · {total_cuotas} cuotas 1X2 · "
        f"{r['apuestas_liquidadas']} apuesta(s) del cupón liquidada(s)",
        icon=":material/check_circle:",
    )
    st.rerun()


st.sidebar.title(":material/sports_soccer: Botano")
st.sidebar.caption("Análisis cuantitativo de ligas de fútbol")
if st.sidebar.button("Refrescar datos", icon=":material/refresh:", type="primary", width="stretch"):
    _refrescar_datos()
st.sidebar.caption("Trae partidos, resultados y cuotas al día directo de las fuentes (football-data.org, The Odds API). Hazlo antes de analizar.")

paginas = [
    st.Page(lambda: analizar_partido.render(CFG), title="Analizar partido", icon=":material/sports_soccer:", url_path="analizar-partido", default=True),
    st.Page(lambda: analizar_apuesta.render(CFG), title="Analizar apuesta", icon=":material/receipt_long:", url_path="analizar-apuesta"),
    st.Page(lambda: bet_builder.render(CFG), title="Armar Bet Builder", icon=":material/construction:", url_path="bet-builder"),
    st.Page(lambda: mis_apuestas.render(CFG), title="Mis apuestas", icon=":material/list_alt:", url_path="mis-apuestas"),
    st.Page(lambda: fiabilidad.render(CFG), title="Fiabilidad del modelo", icon=":material/insights:", url_path="fiabilidad"),
    st.Page(lambda: glosario.render(CFG), title="Glosario", icon=":material/menu_book:", url_path="glosario"),
]
cupon.pagina_analizar = paginas[0]
cupon.pagina_mis_apuestas = paginas[3]
pagina_activa = st.navigation(paginas)
pagina_activa.run()

# Se renderiza después de la página activa para reflejar en el mismo rerun
# las selecciones que el usuario acaba de agregar al cupón desde el análisis.
cupon.panel(CFG)

st.sidebar.caption("Herramienta de análisis, no garantía de ganancia.")
