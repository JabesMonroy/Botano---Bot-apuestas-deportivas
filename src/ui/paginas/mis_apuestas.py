from __future__ import annotations

import pandas as pd
import streamlit as st

from src.apuestas import (
    actualizar, analiticas, editar, editar_combinada, eliminar, eliminar_combinada,
    historial, historial_combinadas, marcar_resultado, resumen_dict, revertir_resultado,
)
from src.config import Config
from src.db import turso
from src.db.database import connect
from src.modelo.liquidacion import MERCADOS_AUTOMATICOS

_ETIQUETA_MERCADO = {
    "1X2": "1X2", "doble_oportunidad": "Doble oportunidad", "totals": "Goles totales",
    "goles_local": "Goles local", "goles_visita": "Goles visita", "btts": "Ambos anotan",
    "primer_gol": "Primer gol", "corners_totales": "Córners", "tarjetas_totales": "Tarjetas",
    "tiros_totales": "Tiros", "tiros_arco_totales": "Tiros al arco", "saques_totales": "Saques de meta",
}

_OPCIONES_RESULTADO = ["pendiente", "ganada", "perdida"]


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


def _etiqueta_mercado(mercado: str) -> str:
    etq = _ETIQUETA_MERCADO.get(mercado, mercado)
    return etq if mercado in MERCADOS_AUTOMATICOS else f"{etq} · manual"


def _filas_tabla(sencillas: list[dict], combinadas: list[dict]) -> list[dict]:
    raiz = [("sencilla", s["fecha"], s) for s in sencillas] + [("combinada", c["fecha"], c) for c in combinadas]
    raiz.sort(key=lambda t: t[1] or "", reverse=True)

    filas = []
    for tipo, _fecha, obj in raiz:
        if tipo == "sencilla":
            filas.append({
                "ID": f"S{obj['id']}", "Tipo": "Sencilla",
                "Detalle": f"{obj['nl']} vs {obj['nv']} — {_etiqueta_mercado(obj['mercado'])}: {obj['seleccion']}",
                "Cuota": obj["cuota_betano"], "Stake": obj["stake"],
                "Resultado": obj["resultado"] or "pendiente", "Ganancia": obj["ganancia"],
                "Fecha": (obj["fecha"] or "")[:16].replace("T", " "),
                "_id_real": obj["id"], "_tipo_real": "sencilla",
            })
        else:
            partidos = ", ".join(dict.fromkeys(f"{p['nl']} vs {p['nv']}" for p in obj["patas"]))
            filas.append({
                "ID": f"C{obj['id']}", "Tipo": "Combinada",
                "Detalle": f"{partidos} ({len(obj['patas'])} patas)",
                "Cuota": obj["cuota_total"], "Stake": obj["stake"],
                "Resultado": obj["resultado"] or "pendiente", "Ganancia": obj["ganancia"],
                "Fecha": (obj["fecha"] or "")[:16].replace("T", " "),
                "_id_real": obj["id"], "_tipo_real": "combinada",
            })
            for p in obj["patas"]:
                filas.append({
                    "ID": f"C{obj['id']}·{p['id']}", "Tipo": "↳ pata",
                    "Detalle": f"{p['nl']} vs {p['nv']} — {_etiqueta_mercado(p['mercado'])}: {p['seleccion']}",
                    "Cuota": p["cuota_betano"], "Stake": None,
                    "Resultado": p["resultado"] or "pendiente", "Ganancia": None,
                    "Fecha": "",
                    "_id_real": p["id"], "_tipo_real": "pata",
                })
    return filas


def _iguales(a, b) -> bool:
    if a is None or (isinstance(a, float) and pd.isna(a)):
        return b is None or (isinstance(b, float) and pd.isna(b))
    if b is None or (isinstance(b, float) and pd.isna(b)):
        return False
    return round(float(a), 2) == round(float(b), 2)


def _guardar_cambios(cfg: Config, original: pd.DataFrame, editado: pd.DataFrame) -> int:
    cambios = 0
    conn = turso.connect(cfg)
    try:
        for i in range(len(original)):
            orig, nuevo = original.iloc[i], editado.iloc[i]
            tipo_real, id_real = orig["_tipo_real"], int(orig["_id_real"])

            if tipo_real != "pata" and (not _iguales(orig["Cuota"], nuevo["Cuota"]) or not _iguales(orig["Stake"], nuevo["Stake"])):
                nueva_cuota = float(nuevo["Cuota"])
                nuevo_stake = None if pd.isna(nuevo["Stake"]) else float(nuevo["Stake"])
                if tipo_real == "sencilla":
                    editar(conn, id_real, nueva_cuota, nuevo_stake)
                else:
                    editar_combinada(conn, id_real, nueva_cuota, nuevo_stake or 0.0)
                cambios += 1

            if tipo_real in ("sencilla", "pata") and nuevo["Resultado"] != orig["Resultado"]:
                if nuevo["Resultado"] == "pendiente":
                    revertir_resultado(conn, id_real)
                else:
                    marcar_resultado(conn, id_real, nuevo["Resultado"] == "ganada")
                cambios += 1
    finally:
        conn.close()
    return cambios


def render(cfg: Config) -> None:
    st.title("Mis apuestas")

    if st.button("Actualizar resultados ahora", icon=":material/refresh:", type="primary"):
        conn_apuestas = turso.connect(cfg)
        conn_partidos = connect(cfg.db_path)
        try:
            n = actualizar(conn_apuestas, conn_partidos)
        finally:
            conn_apuestas.close()
            conn_partidos.close()
        st.toast(f"{n} apuesta(s) actualizada(s)", icon=":material/check_circle:")
        st.rerun()
    st.caption(
        "Liquida automáticamente 1X2, doble oportunidad, goles totales, goles por equipo y ambos anotan, comparando "
        "con el resultado real. **Córners, tarjetas, tiros y saques de meta no tienen fuente de datos reales del "
        "partido ya jugado** (football-data.org no los expone en el plan gratis): marca esas filas a mano en la tabla."
    )

    conn = turso.connect(cfg)
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

    st.markdown("#### Apuestas")
    filas = _filas_tabla(sencillas, combinadas)
    if not filas:
        st.caption("Todavía no hay apuestas registradas.")
    else:
        st.caption(
            "Edita Cuota, Stake o Resultado directamente en la tabla y presiona **Guardar cambios**. Las combinadas "
            "aparecen con sus patas debajo (↳); el resultado de una combinada se calcula solo de sus patas, no se edita ahí."
        )
        df_original = pd.DataFrame(filas)
        editado = st.data_editor(
            df_original,
            column_order=["ID", "Tipo", "Detalle", "Cuota", "Stake", "Resultado", "Ganancia", "Fecha"],
            column_config={
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                "Detalle": st.column_config.TextColumn("Detalle", width="large"),
                "Cuota": st.column_config.NumberColumn("Cuota", min_value=1.01, max_value=10000.0, step=0.01, format="%.2f"),
                "Stake": st.column_config.NumberColumn("Stake (COP)", min_value=0.0, step=1000.0, format="%.0f"),
                "Resultado": st.column_config.SelectboxColumn("Resultado", options=_OPCIONES_RESULTADO, required=True),
                "Ganancia": st.column_config.NumberColumn("Ganancia", format="%.0f"),
                "Fecha": st.column_config.TextColumn("Fecha"),
            },
            disabled=["ID", "Tipo", "Detalle", "Ganancia", "Fecha"],
            hide_index=True,
            width="stretch",
            key="editor_apuestas",
        )
        if st.button("Guardar cambios", icon=":material/save:", type="primary"):
            n = _guardar_cambios(cfg, df_original, editado)
            if n:
                st.toast(f"{n} cambio(s) guardado(s)", icon=":material/check_circle:")
                st.rerun()
            else:
                st.toast("Sin cambios para guardar", icon=":material/info:")

        raices = [f for f in filas if f["_tipo_real"] != "pata"]
        with st.expander("Eliminar una apuesta o combinada"):
            a_eliminar = st.multiselect(
                "Selecciona qué eliminar", [f["ID"] for f in raices],
                format_func=lambda k: next(f"{f['ID']} — {f['Detalle']}" for f in raices if f["ID"] == k),
                key="ids_a_eliminar",
            )
            if a_eliminar and st.button("Eliminar seleccionadas", icon=":material/delete:"):
                conn = turso.connect(cfg)
                try:
                    for clave in a_eliminar:
                        f = next(x for x in raices if x["ID"] == clave)
                        if f["_tipo_real"] == "sencilla":
                            eliminar(conn, f["_id_real"])
                        else:
                            eliminar_combinada(conn, f["_id_real"])
                finally:
                    conn.close()
                st.toast(f"{len(a_eliminar)} eliminada(s)", icon=":material/check_circle:")
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
