# Botano — Bot de análisis de apuestas (Mundial 2026)

Agente analista cuantitativo para el Mundial 2026. Plan y razonamiento en
[prompt_maestro_agente_mundial2026.md](prompt_maestro_agente_mundial2026.md); reglas de trabajo en [CLAUDE.md](CLAUDE.md).

Pipeline: **5 fuentes de datos → mapeo de 48 selecciones → modelo de goles Dixon-Coles (fuerzas + Elo) → evaluación anti-sesgo → reporte / bet builder / simulación de torneo → CLV**.

## Arquitectura de fuentes

| Rol | Fuente |
|---|---|
| Cuotas, calendario, outright | The Odds API (incluye Pinnacle) |
| Resultados, standings | football-data.org |
| Elo de selecciones | eloratings.net |
| Histórico 2022-24 (calibración) | API-Football (free) |
| Clima | OpenWeatherMap |

> API-Football free **no cubre 2026** (solo histórico). Sofascore y FBref están bloqueados por anti-bot (no se evaden).

## Estructura

```
src/
  config.py            .env y rutas
  db/                  esquema SQLite + conexión
  clients/             API-Football, The Odds API, football-data, OpenWeather (cache + rate limit)
  scrapers/            eloratings.net
  mapeo.py             tabla maestra de 48 selecciones (clave FIFA)
  ingesta.py           partidos, resultados, standings, cuotas del Mundial
  historico.py         partidos de selección 2022-24
  modelo/
    dixon_coles.py     matriz de marcadores, mercados, Ajustes
    fuerzas.py         estimación ataque/defensa (MV ponderada en tiempo, anclada al Elo)
    parametros.py      carga/persistencia de parámetros
    calibracion.py     ajuste contra no-vig de Pinnacle
    evaluacion.py      RPS y métricas
    valor.py           no-vig, EV, Kelly, corrección de empate, shrinkage
    bet_builder.py     probabilidad conjunta por correlación
    torneo.py          simulación Monte Carlo
  reporte.py           análisis 1X2 + markdown
  apuestas.py          log, Kelly, CLV
scripts/               puntos de entrada (ver runbook)
data/                  bd, caché, referencia/, modelos/, partidos/ (snapshots)
```

## Puesta en marcha

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # pegar API_FOOTBALL_KEY, ODDS_API_KEY, OPENWEATHER_KEY, FOOTBALL_DATA_KEY
python -m scripts.init_db
python -m scripts.validar_apis
```

## Carga inicial (una vez)

```
python -m scripts.cargar_mapeo        # 48 selecciones
python -m scripts.actualizar          # partidos, resultados, standings, cuotas del Mundial
python -m scripts.ingestar_elo        # Elo de las 48
python -m scripts.ingestar_valor      # valor de plantilla (Transfermarkt, proxy de calidad)
python -m scripts.ingestar_historico  # ~1900 partidos de selección 2022-24 (consume API-Football)
python -m scripts.estimar_fuerzas     # fuerzas Dixon-Coles ancladas al Elo
python -m scripts.calibrar_sesgo      # corrección de empate + shrinkage
python -m scripts.calibrar_valor      # peso del valor de plantilla (calibrado al mercado)
```

## Uso diario

```
python -m scripts.actualizar                  # refresca datos en vivo del Mundial
python -m scripts.generar_reporte ARG AUT     # reporte pre-partido (guarda en data/partidos/)
python -m scripts.analizar_partido ESP KSA    # análisis rápido en consola
python -m scripts.bet_builder ARG-AUT:1 ARG-AUT:under2.5 @2.10   # combinada con correlación
python -m scripts.simular_torneo 20000        # P(avanza)/P(campeón) vs mercado
python -m scripts.registrar_apuesta ARG AUT 1 1.62 10           # registrar apuesta de Betano
python -m scripts.clv                          # actualizar cierre/CLV/resultados y ver historial
```

## Limitaciones conocidas

- El modelo cuantitativo **no bate al mercado sharp** (Pinnacle); su valor real requiere datos de plantilla/forma (bloqueados). Un **guardarraíl** evita reportar EV cuando el modelo diverge >18pp del mercado.
- Sesgo de calendario/inter-confederación: el anclaje al Elo lo mitiga pero no lo elimina.
- `P(campeón)` de la simulación amplifica los sesgos: usar el mercado para outrights.
- Herramienta de análisis, no garantía de ganancia.
```
