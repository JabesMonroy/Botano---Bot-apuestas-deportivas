from __future__ import annotations

import json

import streamlit as st

from src.config import Config
from src.ligas import POR_CODIGO


@st.cache_data(show_spinner=False, ttl=300)
def evaluar(cfg: Config, liga: dict) -> dict:
    codigo = liga["codigo"]
    cfg_liga = POR_CODIGO.get(codigo)
    fuerzas_ruta = cfg.data_dir / "modelos" / f"fuerzas_club_{codigo}.json"
    if not fuerzas_ruta.exists():
        return {
            "nivel": "no disponible",
            "razones": ["Datos históricos insuficientes para ajustar el modelo todavía (mínimo 380 partidos)."],
        }
    fuerzas = json.loads(fuerzas_ruta.read_text(encoding="utf-8"))
    razones = [f"{fuerzas['n_partidos']} partidos históricos usados para estimar fuerzas de ataque/defensa."]
    nivel = "media"

    backtest_ruta = cfg.data_dir / "modelos" / f"backtest_club_{codigo}.json"
    if backtest_ruta.exists():
        bt = json.loads(backtest_ruta.read_text(encoding="utf-8"))
        gap = bt["rps_modelo_cc"] - bt["rps_cierre"]
        razones.append(
            f"Backtest walk-forward validado ({bt['n']} partidos): RPS modelo {bt['rps_modelo_cc']} vs "
            f"cierre de Pinnacle {bt['rps_cierre']} (gap {gap:+.4f})."
        )
        nivel = "alta"
    else:
        razones.append("Sin backtest walk-forward corrido todavía contra el cierre de mercado.")

    if not (cfg_liga and cfg_liga.odds_api):
        razones.append("Sin cuotas de mercado (Pinnacle/The Odds API): solo probabilidades, no se puede calcular EV.")
        nivel = "baja"
    if cfg_liga and cfg_liga.fuente_calendario:
        razones.append(f"Calendario en vivo vía {cfg_liga.fuente_calendario}.")
    else:
        razones.append("Sin calendario en vivo: elige los equipos a mano, no hay próximos partidos automáticos.")
        nivel = "baja"
    if not (cfg_liga and cfg_liga.understat):
        razones.append("Sin xG real por partido (Understat): el modelo se ajusta solo con goles.")
    if not (cfg_liga and cfg_liga.fd_uk):
        razones.append("Sin córners/tarjetas históricos: esos mercados secundarios no están disponibles.")

    return {"nivel": nivel, "razones": razones}


ICONO_NIVEL = {
    "alta": ":material/verified:",
    "media": ":material/info:",
    "baja": ":material/warning:",
    "no disponible": ":material/block:",
}

COLOR_NIVEL = {"alta": "green", "media": "blue", "baja": "orange", "no disponible": "red"}
