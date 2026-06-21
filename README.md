# Botano — Bot de análisis de apuestas (Mundial 2026)

Agente analista cuantitativo de apuestas deportivas. Plan, fuentes y reglas en
[prompt_maestro_agente_mundial2026.md](prompt_maestro_agente_mundial2026.md).
Reglas de trabajo en [CLAUDE.md](CLAUDE.md).

## Estructura

```
src/
  config.py            carga de .env y rutas
  db/                  esquema SQLite y conexión
  clients/             clientes HTTP (caché + rate limit)
    base.py            cliente base cacheado
    api_football.py    fixtures, H2H, estadísticas, alineaciones, lesiones
    odds_api.py        cuotas (Pinnacle) vía The Odds API
    weather.py         pronóstico por estadio (OpenWeatherMap)
scripts/
  init_db.py           crea data/bot.db
  validar_apis.py      valida conectividad y cuotas de las 3 APIs
data/                  bd, caché y snapshots (ignorados en git salvo modelos)
```

## Puesta en marcha

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m scripts.init_db
python -m scripts.validar_apis
```

Pegar las claves en `.env` antes de `validar_apis`:
API-Football (api-sports.io), The Odds API y OpenWeatherMap.
