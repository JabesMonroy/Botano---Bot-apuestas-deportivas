from __future__ import annotations

import streamlit as st

from src.config import Config
from src.ui import fiabilidad as fiabilidad_mod


def _etiqueta_calendario(liga: dict, proximo: dict) -> str:
    info = proximo.get(liga["id"])
    if not info:
        return ":material/event_busy: Sin calendario en vivo"
    if info["dias"] <= 0:
        return f":material/bolt: Hoy · {info['n']} partido(s)"
    if info["dias"] == 1:
        return ":material/bolt: Mañana"
    return f":material/event: {info['fecha']} (en {info['dias']}d)"


def selector_competicion(cfg: Config, ligas: list[dict], proximo: dict, key: str, columnas: int = 4) -> dict:
    nombres = [l["nombre"] for l in ligas]
    if key not in st.session_state or st.session_state[key] not in nombres:
        st.session_state[key] = nombres[0]

    cols = st.columns(columnas)
    for i, liga in enumerate(ligas):
        seleccionada = st.session_state[key] == liga["nombre"]
        fiab = fiabilidad_mod.evaluar(cfg, liga)
        with cols[i % columnas]:
            with st.container(border=True):
                if liga.get("emblema_url"):
                    li, ln = st.columns([1, 4])
                    li.image(liga["emblema_url"], width=32)
                    ln.markdown(f"**{liga['nombre']}**")
                else:
                    st.markdown(f":material/sports_soccer: **{liga['nombre']}**")
                st.caption(_etiqueta_calendario(liga, proximo))
                st.caption(f"{fiabilidad_mod.ICONO_NIVEL[fiab['nivel']]} Fiabilidad {fiab['nivel']}")
                if st.button(
                    "Elegida" if seleccionada else "Elegir",
                    key=f"{key}_card_{liga['codigo'] or liga['nombre']}",
                    type="primary" if seleccionada else "secondary",
                    width="stretch",
                    icon=":material/check_circle:" if seleccionada else ":material/radio_button_unchecked:",
                ):
                    st.session_state[key] = liga["nombre"]
                    st.rerun()

    return next(l for l in ligas if l["nombre"] == st.session_state[key])
