from __future__ import annotations

import streamlit as st

from src.config import Config
from src.db.database import connect
from src.reporte import analizar_club, contexto_partido
from src.ui import datos, fiabilidad, selector_liga
from src.ui.componentes import mostrar_analisis


def render(cfg: Config) -> None:
    ligas = datos.cargar_ligas(cfg)
    if not ligas:
        st.warning("No hay competiciones cargadas. Corre `python -m scripts.cargar_mapeo_clubes`.", icon=":material/warning:")
        return
    proximo = datos.proximo_por_liga(cfg)
    ligas_ordenadas = sorted(ligas, key=lambda l: proximo.get(l["id"], {}).get("dias", 9999))

    st.title("Analizar partido")
    liga = selector_liga.selector_competicion(cfg, ligas_ordenadas, proximo, key="liga_global")
    liga_nombre = liga["nombre"]

    fiab = fiabilidad.evaluar(cfg, liga)
    with st.expander(f"Detalle de fiabilidad de {liga_nombre}: **{fiab['nivel']}**", icon=fiabilidad.ICONO_NIVEL[fiab["nivel"]]):
        for razon in fiab["razones"]:
            st.caption(f"· {razon}")

    equipos = datos.cargar_equipos(cfg, liga["id"])
    nombres = list(equipos)
    if not nombres:
        st.warning("Aún no hay equipos cargados para esta competición. Corre `python -m scripts.cargar_mapeo_clubes`.", icon=":material/warning:")
        return

    if st.session_state.get("liga_actual") != liga_nombre:
        st.session_state.liga_actual = liga_nombre
        st.session_state.sb_local = nombres[0]
        st.session_state.sb_visita = nombres[1] if len(nombres) > 1 else nombres[0]
        st.session_state.pop("analisis_partido", None)

    prox = datos.proximos_partidos(cfg, dias=45, liga_id=liga["id"])
    if prox:
        st.markdown("**:material/bolt: Próximos partidos** — haz clic en uno y se rellenan los equipos (horario de Colombia):")
        por_dia: dict[int, list[dict]] = {}
        for p in prox:
            por_dia.setdefault(p["dia"], []).append(p)
        for dnum in sorted(por_dia)[:3]:
            deldia = por_dia[dnum]
            titulo = f"{deldia[0]['dia_semana'].capitalize()} {deldia[0]['fecha']}"
            st.markdown(f"**{titulo}**")
            cols = st.columns(2)
            for i, p in enumerate(deldia):
                if cols[i % 2].button(f"{p['hora']} · {p['ln']} vs {p['vn']}", key=f"pb_{dnum}_{i}", width="stretch", icon=":material/schedule:"):
                    nl = next((n for n in nombres if equipos[n] == p["lf"]), None)
                    nv = next((n for n in nombres if equipos[n] == p["vf"]), None)
                    if nl:
                        st.session_state.sb_local = nl
                    if nv:
                        st.session_state.sb_visita = nv

    c1, c2 = st.columns(2)
    local = c1.selectbox("Local", nombres, key="sb_local")
    visita = c2.selectbox("Visitante", nombres, key="sb_visita")
    if st.button("Analizar", type="primary", icon=":material/query_stats:"):
        l, v = equipos[local], equipos[visita]
        if l == v:
            st.error("Elige dos equipos distintos.", icon=":material/error:")
            st.session_state.pop("analisis_partido", None)
        else:
            st.session_state.analisis_partido = {
                "liga_id": liga["id"], "liga_codigo": liga["codigo"], "local": l, "visita": v,
            }

    info = st.session_state.get("analisis_partido")
    if info and info["liga_id"] == liga["id"]:
        conn = connect(cfg.db_path)
        a = analizar_club(conn, cfg.data_dir, info["liga_codigo"], info["local"], info["visita"])
        ctx = contexto_partido(conn, info["local"], info["visita"])
        conn.close()
        if a is None:
            st.error(
                "Sin fuerzas ajustadas para esta liga o equipo (recién ascendido). Corre `python -m scripts.estimar_fuerzas_clubes`.",
                icon=":material/error:",
            )
        else:
            mostrar_analisis(cfg, a, ctx)
