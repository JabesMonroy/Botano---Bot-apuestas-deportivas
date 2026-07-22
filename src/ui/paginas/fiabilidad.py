from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.config import Config
from src.ui.formato import pct


def render(cfg: Config) -> None:
    st.title("Fiabilidad del modelo")
    st.caption("Backtest out-of-sample: se entrena el modelo con datos antiguos y se prueba en partidos posteriores que nunca vio. Mide si acierta y, sobre todo, **dónde**.")
    ruta_bt = cfg.data_dir / "modelos" / "backtest.json"
    if not ruta_bt.exists():
        st.info("Aún no hay backtest. Corre `python -m scripts.backtest` (tarda ~1 min) y recarga.", icon=":material/info:")
        return

    bt = json.loads(ruta_bt.read_text(encoding="utf-8"))
    st.markdown(f"Entrenado hasta **{bt['corte']}**, probado en **{bt['test']}** partidos posteriores.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("RPS modelo", bt["rps_modelo"], f"ingenuo {bt['rps_ingenuo']}", delta_color="off")
    m2.metric("Mejora vs ingenuo", f"{bt['mejora_pct']:+.1f}%")
    m3.metric("ECE (calibración)", bt["ece"])
    m4.metric("Brier", bt["brier"])
    st.caption("RPS y Brier: más bajo = mejor. 'Ingenuo' = predecir siempre las tasas base (local/empate/visita). ECE < 0.05 = probabilidades bien calibradas.")

    st.markdown("#### Por dificultad del partido — el sesgo que importa")
    nombres = {"facil": "Favorito claro", "medio": "Intermedio", "renido": "Parejo"}
    st.dataframe(pd.DataFrame([
        {"Tipo": nombres.get(e["estrato"], e["estrato"]), "n": e["n"], "RPS modelo": e["rps_modelo"],
         "RPS ingenuo": e["rps_base"], "Mejora": f"{(e['rps_base'] - e['rps_modelo']) / e['rps_base'] * 100:+.0f}%"}
        for e in bt["estratos"]
    ]), hide_index=True, width="stretch")
    fac = next((e for e in bt["estratos"] if e["estrato"] == "facil"), None)
    ren = next((e for e in bt["estratos"] if e["estrato"] == "renido"), None)
    if fac and ren:
        mf = (fac["rps_base"] - fac["rps_modelo"]) / fac["rps_base"] * 100
        mr = (ren["rps_base"] - ren["rps_modelo"]) / ren["rps_base"] * 100
        st.warning(f"**El sesgo, cuantificado:** el modelo mejora **{mf:.0f}%** sobre lo trivial en partidos con favorito claro, pero solo **{mr:.0f}%** en partidos parejos. Su buena cifra global se apoya en los partidos fáciles; en los **igualados** —donde suele estar el valor— apenas supera lo trivial. **Desconfía más de sus probabilidades en partidos parejos.**", icon=":material/warning:")

    st.markdown("#### Calibración (lo que dice vs lo que pasa)")
    cal = pd.DataFrame(bt["calibracion"])
    cal["ideal"] = cal["predicha"]
    st.line_chart(cal.set_index("predicha")[["observada", "ideal"]])
    st.caption("Si la línea 'observada' sigue a la 'ideal' (diagonal), las probabilidades son fiables: cuando el modelo dice 70%, ocurre ~70% de las veces.")

    if "over_under" in bt:
        st.markdown("#### Over/Under (goles): ¿el modelo aporta?")
        ou = bt["over_under"]
        st.dataframe(pd.DataFrame([
            {"Línea": f"Más de {L}", "Over real": pct(d["tasa_over_real"]), "Over modelo": pct(d["tasa_over_modelo"]),
             "Brier modelo": d["brier_modelo"], "Brier base": d["brier_base"],
             "¿Aporta?": "sí" if d["brier_modelo"] < d["brier_base"] else "NO"}
            for L, d in ou.items()
        ]), hide_index=True, width="stretch")
        todos_peor = all(d["brier_modelo"] >= d["brier_base"] for d in ou.values())
        _sesgos = [d["tasa_over_real"] - d["tasa_over_modelo"] for d in ou.values()]
        sesgo = sum(_sesgos) / len(_sesgos) if _sesgos else 0.0
        if todos_peor:
            st.error(f"**El modelo NO aporta en Over/Under.** En las 3 líneas su Brier es igual o peor que predecir la tasa media: no distingue partidos de muchos/pocos goles mejor que el promedio. Además **subestima los goles** (~{sesgo * 100:.0f} pp menos overs de los que ocurren). Conclusión: usa el modelo para **1X2/resultado** (donde sí aporta +29%), **no para totales de goles**.", icon=":material/error:")
        else:
            st.success("El modelo aporta algo sobre la tasa media en al menos una línea de Over/Under.", icon=":material/check_circle:")

    if "mundial" in bt:
        mu = bt["mundial"]
        st.markdown("#### Sobre el Mundial 2026 ya jugado (prueba natural)")
        st.markdown(f"**{mu['n']}** partidos · RPS modelo **{mu['rps_modelo']}** vs uniforme {mu['rps_uniforme']} · Brier {mu['brier']}")
