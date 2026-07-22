from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import Config
from src.db.database import connect
from src.modelo.valor import ev
from src.reporte import analizar_club
from src.ui import datos, selector_liga
from src.ui.formato import pct
from src.ui.mercados import MERCADOS_COMBI, desglose, prob_individual, prob_partido_combi


def _seccion_sencilla(cfg: Config, liga_codigo: str, equipos: dict, nombres: list[str]) -> None:
    st.header("Analizar sencilla")
    st.caption("Una sola captura, de un mismo partido (uno o varios mercados).")
    from streamlit_paste_button import paste_image_button
    pegar = paste_image_button("Pegar captura (Ctrl+V)", errors="ignore")
    archivo = st.file_uploader("…o sube el archivo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    texto_manual = st.text_area("…o pega aquí el texto de la captura (cópialo con el OCR de tu móvil: mantén pulsado sobre la imagen)", key="cap_texto", height=80)
    imagen_bytes = None
    if pegar.image_data is not None:
        import io as _io
        _buf = _io.BytesIO()
        pegar.image_data.save(_buf, format="PNG")
        imagen_bytes = _buf.getvalue()
    elif archivo:
        imagen_bytes = archivo.getvalue()
    if not (imagen_bytes or texto_manual.strip()):
        return

    from src.lector import analizar, ocr
    if texto_manual.strip():
        texto = texto_manual
    else:
        try:
            with st.spinner("Leyendo la imagen..."):
                texto = ocr(imagen_bytes)
        except Exception as exc:
            st.error(f"No se pudo leer la imagen: {exc}", icon=":material/error:")
            texto = ""
    if not texto:
        return

    local, visita, detectados = analizar(texto, datos.equipos_busqueda(cfg))
    with st.expander("Texto leído por el OCR (revisa si algo se detectó mal)"):
        st.text(texto)
    if not local or not visita:
        st.warning("No detecté dos equipos con claridad. Prueba con una captura más nítida o usa el modo manual de abajo.", icon=":material/warning:")
        return

    st.success(f"Detectado: **{local[1]} vs {visita[1]}** · {len(detectados)} mercado(s)", icon=":material/check_circle:")
    cl = next((n for n in nombres if equipos[n] == local[0]), nombres[0])
    cv = next((n for n in nombres if equipos[n] == visita[0]), nombres[1])
    c1, c2 = st.columns(2)
    loc = c1.selectbox("Local", nombres, index=nombres.index(cl), key="cap_l")
    vis = c2.selectbox("Visitante", nombres, index=nombres.index(cv), key="cap_v")
    pre = [m for m in detectados if m in MERCADOS_COMBI]
    mer_sel = st.multiselect("Mercados (ajusta si el OCR falló)", list(MERCADOS_COMBI), default=pre, key="ms_" + local[0] + visita[0] + "_" + "_".join(pre))
    cuota = st.number_input("Cuota combinada de Betano (0 = no la tengo)", 0.0, 10000.0, 0.0, step=0.05, key="cap_cuota")
    if st.button("Calcular combinada", type="primary", key="cap_calc", icon=":material/calculate:") and mer_sel:
        conn = connect(cfg.db_path)
        a = analizar_club(conn, cfg.data_dir, liga_codigo, equipos[loc], equipos[vis])
        conn.close()
        if a is None:
            st.error("Sin datos para ese partido.", icon=":material/error:")
        else:
            corr, naive = prob_partido_combi(a, [MERCADOS_COMBI[m] for m in mer_sel])
            st.markdown("**Desglose: cómo baja con cada selección**")
            st.table(desglose([(m, prob_individual(a, MERCADOS_COMBI[m])) for m in mer_sel]))
            m1, m2 = st.columns(2)
            m1.metric("Probabilidad de la combinada", pct(corr), f"naive: {pct(naive)}")
            m2.metric("Cuota justa del modelo", f"{1 / corr:.2f}" if corr > 0 else "—")
            if cuota and cuota > 1:
                st.metric("Valor (EV)", f"{ev(corr, cuota):+.3f}" if a.fiable else "n/f")
            st.info(f"**Por qué parece bajo:** la combinada se cumple solo si ocurren **las {len(mer_sel)} selecciones a la vez**, así que sus probabilidades se multiplican. Cada pata añadida baja la probabilidad total y sube la cuota. Tiene valor solo si tu cuota supera la justa del modelo.", icon=":material/info:")


def _seccion_combinada(cfg: Config, liga_codigo: str, equipos: dict, nombres: list[str]) -> None:
    st.header("Analizar combinada")
    st.caption("Pega (Ctrl+V) o sube una o varias capturas de una combinada con partidos distintos. El bot detecta cada partido con su mercado; revísalo y corrige en la tabla antes de calcular.")
    from streamlit_paste_button import paste_image_button
    pegar_m = paste_image_button("Pegar captura (Ctrl+V)", errors="ignore", key="multi_paste")
    multi = st.file_uploader("…o sube el/los archivo(s) (PNG/JPG)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="multi_up")
    texto_manual_m = st.text_area("…o pega aquí el texto de la combinada (cópialo con el OCR de tu móvil)", key="multi_texto", height=100)
    imagenes = []
    if pegar_m.image_data is not None:
        import io as _io2
        _b = _io2.BytesIO()
        pegar_m.image_data.save(_b, format="PNG")
        imagenes.append(("(pegada)", _b.getvalue()))
    for f in multi or []:
        imagenes.append((f.name, f.getvalue()))
    if not (imagenes or texto_manual_m.strip()):
        return

    import src.lector as _lm
    eqs = datos.equipos_busqueda(cfg)
    detectadas, textos = [], []
    if texto_manual_m.strip():
        textos.append(texto_manual_m)
        detectadas.extend(_lm.analizar_multi(texto_manual_m, eqs))
    for nombre, dat in imagenes:
        try:
            with st.spinner(f"Leyendo {nombre}..."):
                txt = _lm.ocr(dat)
        except Exception as exc:
            st.error(f"No se pudo leer {nombre}: {exc}", icon=":material/error:")
            continue
        textos.append(txt)
        detectadas.extend(_lm.analizar_multi(txt, eqs))
    with st.expander("Texto leído por el OCR (revisa si algo se detectó mal)"):
        for txt in textos:
            st.text(txt)
    if any("anotar en cualquier" in t.lower() or "marcar en cualquier" in t.lower() for t in textos):
        st.warning("Detecté mercado(s) de **goleador** (p. ej. *Anotar en cualquier momento*). El modelo Dixon-Coles no estima goles por jugador, así que **no se incluyen** en el cálculo: valóralos aparte.", icon=":material/warning:")
    cuota_detectada = next((c for c in (_lm.cuota_total(t) for t in textos) if c), 0.0) or 0.0
    vistas, filas_init = set(), []
    for loc, vis, m, cu in detectadas:
        clave = (loc[0], vis[0], m)
        if clave not in vistas:
            vistas.add(clave)
            filas_init.append({
                "Local": next((n for n in nombres if equipos[n] == loc[0]), nombres[0]),
                "Visitante": next((n for n in nombres if equipos[n] == vis[0]), nombres[1]),
                "Mercado": m,
                "Cuota Betano": float(cu) if cu else 0.0,
            })
    if not filas_init:
        st.warning("No detecté partidos con claridad. Añade las filas a mano en la tabla de abajo.", icon=":material/warning:")
        filas_init = [{"Local": nombres[0], "Visitante": nombres[1], "Mercado": list(MERCADOS_COMBI)[0], "Cuota Betano": 0.0}]
    st.markdown("**Selecciones detectadas** — corrige equipos/mercados/cuota o añade filas (botón +):")
    editor = st.data_editor(
        pd.DataFrame(filas_init), num_rows="dynamic", hide_index=True, width="stretch", key="multi_editor",
        column_config={
            "Local": st.column_config.SelectboxColumn(options=nombres, required=True),
            "Visitante": st.column_config.SelectboxColumn(options=nombres, required=True),
            "Mercado": st.column_config.SelectboxColumn(options=list(MERCADOS_COMBI), required=True),
            "Cuota Betano": st.column_config.NumberColumn(format="%.2f", help="Cuota de Betano de la selección (o del Bet Builder). 0 = no la tengo."),
        },
    )
    cuota_x = st.number_input("Cuota TOTAL de la combinada en Betano (0 = no la tengo)", 0.0, 100000.0, float(cuota_detectada), step=0.05, key="multi_cuota")
    if st.button("Calcular combinada", type="primary", key="multi_calc", icon=":material/calculate:"):
        grupos: dict = {}
        cuotas_item: dict = {}
        for _, fila in editor.iterrows():
            if fila["Local"] in equipos and fila["Visitante"] in equipos and fila["Mercado"] in MERCADOS_COMBI:
                clave_p = (equipos[fila["Local"]], equipos[fila["Visitante"]])
                grupos.setdefault(clave_p, []).append(fila["Mercado"])
                cu = fila.get("Cuota Betano", 0) or 0
                if cu > 1 and clave_p not in cuotas_item:
                    cuotas_item[clave_p] = float(cu)
        conn = connect(cfg.db_path)
        p_corr, fiable, filas_res, ok = 1.0, True, [], True
        for (l, v), mers in grupos.items():
            a = analizar_club(conn, cfg.data_dir, liga_codigo, l, v)
            if a is None:
                st.error(f"Sin datos para {l}-{v}.", icon=":material/error:")
                ok = False
                break
            corr, _ = prob_partido_combi(a, [MERCADOS_COMBI[m] for m in mers])
            p_corr *= corr
            fiable = fiable and a.fiable
            cu_item = cuotas_item.get((l, v))
            ev_item = ev(corr, cu_item) if (cu_item and a.fiable) else None
            filas_res.append({
                "Partido": f"{a.nombre_local}-{a.nombre_visita}",
                "Mercado(s)": ", ".join(mers),
                "Prob. modelo": pct(corr),
                "Cuota Betano": f"{cu_item:.2f}" if cu_item else "—",
                "Cuota justa": f"{1 / corr:.2f}" if corr > 0 else "—",
                "EV": f"{ev_item:+.1%}" if ev_item is not None else ("n/f" if cu_item else "—"),
            })
        conn.close()
        if ok and filas_res:
            st.markdown("**Valor por selección (probabilidad del modelo vs cuota real de Betano)**")
            st.dataframe(pd.DataFrame(filas_res), hide_index=True, width="stretch")
            m1, m2, m3 = st.columns(3)
            m1.metric("Prob. de la combinada", pct(p_corr))
            m2.metric("Cuota justa del modelo", f"{1 / p_corr:.2f}" if p_corr > 0 else "—")
            if cuota_x and cuota_x > 1:
                m3.metric("EV de la combinada", f"{ev(p_corr, cuota_x):+.1%}" if fiable else "n/f")
                st.caption(f"Betano paga **{cuota_x:.2f}** vs cuota justa **{1 / p_corr:.2f}**. " + ("Tiene valor si Betano paga más que la justa." if fiable else "Modelo poco fiable en algún partido: EV no válido."))
            buenas = [f for f in filas_res if f["EV"] not in ("—", "n/f") and not f["EV"].startswith("-")]
            if buenas:
                st.success("Selecciones con valor (EV+): " + " · ".join(f"{f['Partido']} {f['Mercado(s)']} ({f['EV']})" for f in buenas), icon=":material/check_circle:")


def _seccion_manual(cfg: Config, liga_codigo: str, equipos: dict, nombres: list[str]) -> None:
    with st.expander("Armar la combinada manualmente (incluye varios partidos)", icon=":material/edit:"):
        n = st.number_input("¿Cuántas selecciones?", 1, 8, 2, key="man_n")
        seleccion = []
        for i in range(int(n)):
            st.markdown(f"**Selección {i + 1}**")
            a1, a2, a3 = st.columns([1, 1, 1.4])
            loc = a1.selectbox("Local", nombres, index=0, key=f"l{i}")
            vis = a2.selectbox("Visitante", nombres, index=1, key=f"v{i}")
            mer = a3.selectbox("Mercado", list(MERCADOS_COMBI), key=f"m{i}")
            seleccion.append((equipos[loc], equipos[vis], mer))
        cuota_m = st.number_input("Cuota combinada de Betano (0 = no la tengo)", 0.0, 10000.0, 0.0, step=0.05, key="man_cuota")
        if st.button("Calcular", type="primary", key="man_calc", icon=":material/calculate:"):
            grupos: dict = {}
            for l, v, mer in seleccion:
                grupos.setdefault((l, v), []).append(mer)
            conn = connect(cfg.db_path)
            p_corr, p_naive, fiable, pares, ok = 1.0, 1.0, True, [], True
            for (l, v), nombres_mercado in grupos.items():
                a = analizar_club(conn, cfg.data_dir, liga_codigo, l, v)
                if a is None:
                    st.error(f"Sin datos para {l}-{v}.", icon=":material/error:")
                    ok = False
                    break
                corr, naive = prob_partido_combi(a, [MERCADOS_COMBI[nm] for nm in nombres_mercado])
                p_corr *= corr
                p_naive *= naive
                fiable = fiable and a.fiable
                for nm in nombres_mercado:
                    pares.append((f"{l}-{v}: {nm}", prob_individual(a, MERCADOS_COMBI[nm])))
            conn.close()
            if ok:
                st.markdown("**Desglose: cómo baja con cada selección**")
                st.table(desglose(pares))
                m1, m2 = st.columns(2)
                m1.metric("Probabilidad combinada (correcta)", pct(p_corr), f"naive: {pct(p_naive)}")
                if cuota_m and cuota_m > 1:
                    m2.metric("Valor (EV)", f"{ev(p_corr, cuota_m):+.3f}" if fiable else "n/f")
                    st.caption(f"Cuota justa según el modelo: **{1 / p_corr:.2f}**. " + ("Tiene valor solo si tu cuota la supera." if fiable else "Algún partido es poco fiable vs el mercado (EV no válido)."))


def render(cfg: Config) -> None:
    ligas = datos.cargar_ligas(cfg)
    if not ligas:
        st.warning("No hay competiciones cargadas. Corre `python -m scripts.cargar_mapeo_clubes`.", icon=":material/warning:")
        return
    proximo = datos.proximo_por_liga(cfg)
    ligas_ordenadas = sorted(ligas, key=lambda l: proximo.get(l["id"], {}).get("dias", 9999))

    st.title("Analizar apuesta")
    liga = selector_liga.selector_competicion(cfg, ligas_ordenadas, proximo, key="apu_liga")
    st.caption("Lee tu apuesta desde una captura de Betano (recomendado) o ármala a mano. Todas las selecciones deben ser de **esta competición**. "
               "Dentro de un mismo partido se usa la correlación real (matriz Dixon-Coles para goles); córners y tarjetas se tratan como independientes.")

    equipos = datos.cargar_equipos(cfg, liga["id"])
    nombres = list(equipos)
    if not nombres:
        st.warning("Aún no hay equipos cargados para esta competición. Corre `python -m scripts.cargar_mapeo_clubes`.", icon=":material/warning:")
        return

    _seccion_sencilla(cfg, liga["codigo"], equipos, nombres)
    st.divider()
    _seccion_combinada(cfg, liga["codigo"], equipos, nombres)
    st.divider()
    _seccion_manual(cfg, liga["codigo"], equipos, nombres)
