from __future__ import annotations

import streamlit as st

from src.config import Config


def render(cfg: Config) -> None:
    st.title("Qué significa cada término")
    st.markdown(
        """
- **Elo** — fuerza de una selección según sus resultados. 2000+ elite, ~1800 buena, ~1500 floja.
- **xG / xGA** — goles esperados que **genera** / **concede** por partido (calidad de ocasiones). Menos xGA = mejor defensa.
- **Valor plantilla** — valor de mercado de los jugadores (Transfermarkt); aproxima la calidad del plantel.
- **Modelo / Mercado / Apostar** — probabilidad del bot / de la cuota de Pinnacle sin margen / mezcla de ambas (la que se usa para el EV).
- **EV (valor esperado)** — cuánto ganas/pierdes de media por unidad apostada. **+** = hay valor; **−** = la cuota paga poco; **n/f** = el modelo no es fiable ahí (no apostar).
- **Over (+)** — "más de": +9.5 córners = 10 o más; +2.5 goles = 3 o más. El % es la probabilidad.
- **Ambos anotan (BTTS)** — que los dos equipos marquen al menos un gol.
- **CLV** — ¿tu cuota fue mejor que la de cierre del mercado? Si es positivo con el tiempo, vas bien.
        """
    )
