from __future__ import annotations

import streamlit as st

from src.apuestas import registrar_combinada, registrar_directo, partido_id, resumen_dict
from src.config import Config
from src.db.database import connect
from src.modelo.valor import ev

pagina_analizar: st.Page | None = None
pagina_mis_apuestas: st.Page | None = None


def _registrar_sencillas(cfg: Config, items: list[dict]) -> int:
    conn = connect(cfg.db_path)
    registrados = 0
    try:
        for item in items:
            pid = partido_id(conn, item["local"], item["visita"])
            if pid is None:
                continue
            registrar_directo(conn, pid, item["mercado"], item["seleccion"], item["cuota_betano"], item["prob_modelo"], item.get("stake"))
            registrados += 1
    finally:
        conn.close()
    return registrados


def _registrar_combinada(cfg: Config, items: list[dict], cuota_total: float, stake: float) -> bool:
    conn = connect(cfg.db_path)
    try:
        patas = []
        for item in items:
            pid = partido_id(conn, item["local"], item["visita"])
            if pid is None:
                return False
            patas.append({
                "partido_id": pid, "mercado": item["mercado"], "seleccion": item["seleccion"],
                "cuota_betano": item["cuota_betano"], "prob_modelo": item["prob_modelo"],
            })
        registrar_combinada(conn, patas, cuota_total, stake)
    finally:
        conn.close()
    return True


def panel(cfg: Config) -> None:
    cupon = st.session_state.setdefault("cupon", [])
    conn = connect(cfg.db_path)
    try:
        resumen = resumen_dict(conn)
    finally:
        conn.close()

    titulo = f"Mi cupón ({len(cupon)})" if cupon else "Mi cupón"
    with st.sidebar.expander(titulo, icon=":material/receipt_long:", expanded=bool(cupon)):
        if not cupon:
            st.caption("Vacío. Ve a **Analizar partido**, elige equipos y pulsa **Analizar** — arriba del resultado verás un cuadro para agregar la apuesta al cupón con un clic.")
            if pagina_analizar is not None:
                st.page_link(pagina_analizar, label="Ir a Analizar partido", icon=":material/sports_soccer:")
        else:
            for i, item in enumerate(cupon):
                uid = item.setdefault("uid", f"legacy{i}")
                with st.container(border=True):
                    justa = f"{1 / item['prob_modelo']:.2f}" if item["prob_modelo"] > 0 else "—"
                    st.markdown(f"**{item['nombre_local']} vs {item['nombre_visita']}**")
                    st.caption(f"{item['etiqueta']} (probabilidad justa {justa})")
                    item["cuota_betano"] = st.number_input(
                        "Cuota Betano", 1.01, 1000.0, item["cuota_betano"], step=0.01, key=f"cupon_cuota_{uid}",
                    )
                    item["stake"] = st.number_input(
                        "Cuánto aposté (COP)", 0.0, 10_000_000.0, item.get("stake", 10000.0), step=1000.0, format="%.0f", key=f"cupon_stake_{uid}",
                    )
                    item["combinar"] = st.checkbox("Incluir en combinada", value=item.get("combinar", False), key=f"cupon_comb_{uid}")
                    if st.button("Quitar", key=f"cupon_del_{uid}", icon=":material/delete:", width="stretch"):
                        cupon.pop(i)
                        st.rerun()

            marcadas = [it for it in cupon if it.get("combinar")]
            sencillas = [it for it in cupon if not it.get("combinar")]

            if sencillas and st.button(f"Registrar {len(sencillas)} sencilla(s)", type="primary", icon=":material/save:", width="stretch", key="cupon_registrar_sencillas"):
                n = _registrar_sencillas(cfg, sencillas)
                st.session_state.cupon = marcadas
                st.toast(f"{n} apuesta(s) registrada(s) en el historial", icon=":material/check_circle:")
                st.rerun()

            if len(marcadas) == 1:
                st.caption("Marca al menos 2 selecciones para armar una combinada.")
            elif len(marcadas) >= 2:
                st.markdown(f"**Combinada ({len(marcadas)} patas)**")
                cuota_sugerida = 1.0
                prob_naive = 1.0
                for it in marcadas:
                    cuota_sugerida *= it["cuota_betano"]
                    prob_naive *= it["prob_modelo"]
                cuota_total = st.number_input(
                    "Cuota total (la que muestra Betano)", 1.01, 10000.0, round(cuota_sugerida, 2), step=0.01, key="cupon_comb_cuota",
                )
                stake_comb = st.number_input("Cuánto aposté en la combinada (COP)", 0.0, 10_000_000.0, 10000.0, step=1000.0, format="%.0f", key="cupon_comb_stake")
                evv = ev(prob_naive, cuota_total)
                st.caption(
                    f"Probabilidad conjunta (asumiendo independencia): {prob_naive * 100:.1f}% · "
                    f"cuota justa {1 / prob_naive:.2f} · EV {evv:+.3f}"
                )
                if st.button("Registrar combinada", type="primary", icon=":material/save:", width="stretch", key="cupon_registrar_combinada"):
                    if _registrar_combinada(cfg, marcadas, cuota_total, stake_comb):
                        st.session_state.cupon = sencillas
                        st.toast("Combinada registrada en el historial", icon=":material/check_circle:")
                        st.rerun()
                    else:
                        st.error("No se encontró el partido de alguna pata en la base de datos.", icon=":material/error:")

        if resumen["n_pendientes"] or resumen["n_liquidadas"]:
            st.caption(f"**Historial** — {resumen['n_pendientes']} pendiente(s), {resumen['n_liquidadas']} liquidada(s) de {resumen['n_total']} apuestas.")
            if resumen["clv_medio"] is not None:
                st.caption(f"CLV medio: {resumen['clv_medio'] * 100:+.1f}% ({resumen['clv_positivo_pct'] * 100:.0f}% positivo)")
            if resumen["n_liquidadas"]:
                st.caption(f"P/L: {resumen['ganancia_total']:+.0f} · ROI {resumen['roi']:+.1f}%")
            if pagina_mis_apuestas is not None:
                st.page_link(pagina_mis_apuestas, label="Ver todas mis apuestas", icon=":material/receipt_long:")
            st.caption("Corre `python -m scripts.clv` para liquidar automáticamente 1X2, doble oportunidad, goles y BTTS de las pendientes.")
