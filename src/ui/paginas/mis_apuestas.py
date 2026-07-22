from __future__ import annotations

import pandas as pd
import streamlit as st

from src.apuestas import (
    actualizar, analiticas, editar, editar_combinada, eliminar, eliminar_combinada,
    historial, historial_combinadas, marcar_resultado, resumen_dict,
)
from src.config import Config
from src.db.database import connect
from src.modelo.liquidacion import MERCADOS_AUTOMATICOS

_ETIQUETA_MERCADO = {
    "1X2": "1X2", "doble_oportunidad": "Doble oportunidad", "totals": "Goles totales",
    "goles_local": "Goles local", "goles_visita": "Goles visita", "btts": "Ambos anotan",
    "primer_gol": "Primer gol", "corners_totales": "Córners", "tarjetas_totales": "Tarjetas",
    "tiros_totales": "Tiros", "tiros_arco_totales": "Tiros al arco", "saques_totales": "Saques de meta",
}

_FILTROS_ESTADO = {
    "Todas": lambda r: True,
    "Pendientes": lambda r: r is None,
    "Ganadas": lambda r: r == "ganada",
    "Perdidas": lambda r: r == "perdida",
}


def _color_resultado(col):
    estilos = []
    for x in col:
        if x == "ganada":
            estilos.append("color: #1e8449; font-weight: bold")
        elif x == "perdida":
            estilos.append("color: #c0392b; font-weight: bold")
        else:
            estilos.append("color: gray")
    return estilos


def _color_ganancia(col):
    estilos = []
    for x in col:
        if isinstance(x, (int, float)) and x > 0:
            estilos.append("color: #1e8449; font-weight: bold")
        elif isinstance(x, (int, float)) and x < 0:
            estilos.append("color: #c0392b")
        else:
            estilos.append("color: gray")
    return estilos


def _items_unificados(sencillas: list[dict], combinadas: list[dict]) -> list[dict]:
    items = [{
        "clave": f"S{s['id']}", "id": s["id"], "tipo": "Sencilla",
        "detalle": f"{s['nl']} vs {s['nv']} — {_ETIQUETA_MERCADO.get(s['mercado'], s['mercado'])}: {s['seleccion']}",
        "cuota": s["cuota_betano"], "stake": s["stake"], "resultado": s["resultado"],
        "ganancia": s["ganancia"], "fecha": s["fecha"],
    } for s in sencillas]
    for c in combinadas:
        partidos = ", ".join(dict.fromkeys(f"{p['nl']} vs {p['nv']}" for p in c["patas"]))
        items.append({
            "clave": f"C{c['id']}", "id": c["id"], "tipo": "Combinada",
            "detalle": f"{partidos} ({len(c['patas'])} patas)",
            "cuota": c["cuota_total"], "stake": c["stake"], "resultado": c["resultado"],
            "ganancia": c["ganancia"], "fecha": c["fecha"],
        })
    items.sort(key=lambda it: it["fecha"] or "", reverse=True)
    return items


def render(cfg: Config) -> None:
    st.title("Mis apuestas")

    if st.button("Actualizar resultados ahora", icon=":material/refresh:", type="primary"):
        conn = connect(cfg.db_path)
        try:
            n = actualizar(conn)
        finally:
            conn.close()
        st.toast(f"{n} apuesta(s) actualizada(s)", icon=":material/check_circle:")
        st.rerun()
    st.caption(
        "Liquida automáticamente 1X2, doble oportunidad, goles totales, goles por equipo y ambos anotan, comparando "
        "con el resultado real. **Córners, tarjetas, tiros y saques de meta no tienen fuente de datos reales del "
        "partido ya jugado** (football-data.org no los expone en el plan gratis): márcalas a mano abajo."
    )

    conn = connect(cfg.db_path)
    try:
        resumen = resumen_dict(conn)
        sencillas = historial(conn)
        combinadas = historial_combinadas(conn)
        an = analiticas(conn)
    finally:
        conn.close()

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Apuestas totales", resumen["n_total"])
    r2.metric("Pendientes", resumen["n_pendientes"])
    r3.metric("CLV medio", f"{resumen['clv_medio'] * 100:+.1f}%" if resumen["clv_medio"] is not None else "—")
    r4.metric(
        "P/L", f"{resumen['ganancia_total']:+.0f}" if resumen["ganancia_total"] is not None else "—",
        f"ROI {resumen['roi']:+.1f}%" if resumen["roi"] is not None else None,
    )

    items = _items_unificados(sencillas, combinadas)

    st.markdown("#### Apuestas")
    if not items:
        st.caption("Todavía no hay apuestas registradas.")
    else:
        pendientes_sencillas = [s for s in sencillas if s["resultado"] is None]
        pendientes_patas = [p for c in combinadas for p in c["patas"] if p["resultado"] is None]
        if pendientes_sencillas or pendientes_patas:
            st.markdown(f"**{len(pendientes_sencillas) + len(pendientes_patas)} línea(s) por marcar** — márcalas si ya sabes el resultado")
            st.caption("Cuenta cada selección por separado, incluidas las patas de combinadas; el «Pendientes» de arriba cuenta apuestas y combinadas como una sola unidad cada una.")
            for s in pendientes_sencillas:
                c1, c2, c3 = st.columns([4, 1, 1])
                etq = _ETIQUETA_MERCADO.get(s["mercado"], s["mercado"])
                nota = "" if s["mercado"] in MERCADOS_AUTOMATICOS else " · sin dato real, hay que marcarla a mano"
                c1.markdown(f"**{s['nl']} vs {s['nv']}** — {etq}: {s['seleccion']} @ {s['cuota_betano']:.2f}{nota}")
                if c2.button("Ganada", key=f"gano_{s['id']}", icon=":material/check_circle:"):
                    conn = connect(cfg.db_path)
                    marcar_resultado(conn, s["id"], True)
                    conn.close()
                    st.rerun()
                if c3.button("Perdida", key=f"perdio_{s['id']}", icon=":material/cancel:"):
                    conn = connect(cfg.db_path)
                    marcar_resultado(conn, s["id"], False)
                    conn.close()
                    st.rerun()
            for p in pendientes_patas:
                c1, c2, c3 = st.columns([4, 1, 1])
                etq = _ETIQUETA_MERCADO.get(p["mercado"], p["mercado"])
                nota = "" if p["mercado"] in MERCADOS_AUTOMATICOS else " · sin dato real, hay que marcarla a mano"
                c1.markdown(f"**{p['nl']} vs {p['nv']}** — {etq}: {p['seleccion']} (pata de combinada){nota}")
                if c2.button("Ganada", key=f"gano_pata_{p['id']}", icon=":material/check_circle:"):
                    conn = connect(cfg.db_path)
                    marcar_resultado(conn, p["id"], True)
                    conn.close()
                    st.rerun()
                if c3.button("Perdida", key=f"perdio_pata_{p['id']}", icon=":material/cancel:"):
                    conn = connect(cfg.db_path)
                    marcar_resultado(conn, p["id"], False)
                    conn.close()
                    st.rerun()
            st.divider()

        filtro = st.radio("Mostrar", list(_FILTROS_ESTADO), horizontal=True, key="filtro_apuestas")
        items_vista = [it for it in items if _FILTROS_ESTADO[filtro](it["resultado"])]
        if not items_vista:
            st.caption(f"Ninguna apuesta en estado «{filtro.lower()}».")
        else:
            filas = [{
                "ID": it["clave"], "Tipo": it["tipo"], "Detalle": it["detalle"],
                "Cuota": it["cuota"], "Stake": it["stake"],
                "Resultado": it["resultado"] or "pendiente", "Ganancia": it["ganancia"],
                "Fecha": (it["fecha"] or "")[:16].replace("T", " "),
            } for it in items_vista]
            df_items = pd.DataFrame(filas)
            st.dataframe(
                df_items.style.apply(_color_resultado, subset=["Resultado"]).apply(_color_ganancia, subset=["Ganancia"]),
                hide_index=True, width="stretch",
            )

        if combinadas:
            with st.expander("Ver patas de las combinadas"):
                for c in combinadas:
                    etiqueta_estado = {"ganada": ":green[**ganada**]", "perdida": ":red[**perdida**]"}.get(c["resultado"], "**pendiente**")
                    st.markdown(f"**C{c['id']}** — cuota {c['cuota_total']:.2f} · stake {c['stake']:.0f} · {etiqueta_estado}")
                    for p in c["patas"]:
                        etq = _ETIQUETA_MERCADO.get(p["mercado"], p["mercado"])
                        marca = {"ganada": " (:green[ganada])", "perdida": " (:red[perdida])"}.get(p["resultado"], " (pendiente)")
                        st.caption(f"· {p['nl']} vs {p['nv']} — {etq}: {p['seleccion']}{marca}")
                    st.divider()

        with st.expander("Editar o eliminar una apuesta"):
            claves = [it["clave"] for it in items]
            clave_sel = st.selectbox(
                "Apuesta", claves, key="edit_item_clave",
                format_func=lambda k: next(f"{it['clave']} — {it['detalle']}" for it in items if it["clave"] == k),
            )
            item_sel = next(it for it in items if it["clave"] == clave_sel)
            ec1, ec2 = st.columns(2)
            label_cuota = "Cuota total" if item_sel["tipo"] == "Combinada" else "Cuota"
            nueva_cuota = ec1.number_input(label_cuota, 1.01, 10000.0, float(item_sel["cuota"]), step=0.01, key=f"edit_cuota_{clave_sel}")
            nuevo_stake = ec2.number_input(
                "Stake (COP)", 0.0, 10_000_000.0, float(item_sel["stake"] or 0.0), step=1000.0, format="%.0f", key=f"edit_stake_{clave_sel}",
            )
            eb1, eb2 = st.columns(2)
            if eb1.button("Guardar cambios", icon=":material/save:", type="primary", key="btn_editar_item", width="stretch"):
                conn = connect(cfg.db_path)
                if item_sel["tipo"] == "Sencilla":
                    editar(conn, item_sel["id"], nueva_cuota, nuevo_stake)
                else:
                    editar_combinada(conn, item_sel["id"], nueva_cuota, nuevo_stake)
                conn.close()
                st.toast("Apuesta actualizada", icon=":material/check_circle:")
                st.rerun()
            if eb2.button("Eliminar", icon=":material/delete:", key="btn_del_item", width="stretch"):
                conn = connect(cfg.db_path)
                if item_sel["tipo"] == "Sencilla":
                    eliminar(conn, item_sel["id"])
                else:
                    eliminar_combinada(conn, item_sel["id"])
                conn.close()
                st.rerun()

    st.markdown("#### Analíticas")
    if an["n_liquidadas"] == 0:
        st.caption("Todavía no hay apuestas liquidadas para calcular analíticas.")
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric("Acierto", f"{an['tasa_acierto'] * 100:.0f}%" if an["tasa_acierto"] is not None else "—", f"sobre {an['n_liquidadas']} liquidadas")
        k2.metric("EV medio al registrar", f"{an['ev_medio']:+.3f}" if an["ev_medio"] is not None else "—")
        k3.metric("Racha de banca", f"{an['serie_banca'][-1]['banca_acumulada']:+.0f}" if an["serie_banca"] else "—")

        if len(an["serie_banca"]) >= 2:
            df_banca = pd.DataFrame(an["serie_banca"]).set_index("fecha")
            st.line_chart(df_banca, y="banca_acumulada")
            st.caption("Ganancia acumulada (COP) en el orden en que se liquidaron las apuestas, sencillas y combinadas.")

        if an["por_mercado"] or an["resumen_combinadas"]:
            filas_mercado = [{
                "Mercado": _ETIQUETA_MERCADO.get(m["mercado"], m["mercado"]), "N": m["n"],
                "Acierto": f"{m['acierto']:.0f}%" if m["acierto"] is not None else "—",
                "Ganancia": m["ganancia"], "ROI": f"{m['roi']:+.1f}%" if m["roi"] is not None else "—",
            } for m in an["por_mercado"]]
            if an["resumen_combinadas"]:
                rc = an["resumen_combinadas"]
                filas_mercado.append({
                    "Mercado": "Combinadas (agregado)", "N": rc["n"],
                    "Acierto": f"{rc['acierto']:.0f}%" if rc["acierto"] is not None else "—",
                    "Ganancia": rc["ganancia"], "ROI": f"{rc['roi']:+.1f}%" if rc["roi"] is not None else "—",
                })
            st.markdown("**Desempeño por mercado**")
            st.caption(
                "Cada fila de mercado es de apuestas sencillas. Las combinadas se muestran **aparte** ('Combinadas (agregado)'): "
                "su ganancia es del conjunto de patas, no de un mercado individual — mezclarla dentro de cada mercado sobre-contaría el resultado."
            )
            st.dataframe(pd.DataFrame(filas_mercado).style.apply(_color_ganancia, subset=["Ganancia"]), hide_index=True, width="stretch")
