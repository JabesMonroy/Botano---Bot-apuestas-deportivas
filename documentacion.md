# Documentación — Botano (Bot de análisis de apuestas, Mundial 2026)

Documento de referencia de toda la arquitectura: qué hace cada archivo, cómo fluyen los datos y por qué el modelo está construido así. Para el plan conceptual ver [prompt_maestro_agente_mundial2026.md](prompt_maestro_agente_mundial2026.md); para el runbook rápido ver [README.md](README.md).

---

## 1. Qué es y filosofía

Sistema cuantitativo que, para cada partido del Mundial 2026, estima probabilidades de 1X2, Over/Under, BTTS, córners y tarjetas, las compara con la línea *sharp* de Pinnacle y calcula valor esperado (EV). Además simula el torneo (clasificación/campeón) y mide el desempeño real vía CLV.

Principios de diseño:

- **Honestidad sobre optimismo**: cada componente documenta sus sesgos en vez de esconderlos. Si el modelo diverge mucho del mercado, un **guardarraíl** lo marca como no fiable en vez de reportar un EV falso.
- **El mercado como referencia**: Pinnacle (la casa más afilada) es el ancla. Toda incorporación de datos (valor de plantilla, xG) se **calibra contra el mercado**; si no reduce la divergencia, se le da peso cero.
- **Transparencia**: modelo por capas explícitas (no caja negra), con parámetros auditables y persistidos en JSON.

---

## 2. Arquitectura de datos

### 2.1 Fuentes (7)

| Fuente | Acceso | Rol |
|---|---|---|
| The Odds API | API key | Cuotas (Pinnacle), calendario, outright del Mundial |
| football-data.org | API key | Resultados, standings, plantillas convocadas |
| eloratings.net | scraping (TSV) | Elo de selecciones (escala global entre confederaciones) |
| API-Football | API key (free) | Histórico de selección 2022-24 para estimar fuerzas |
| Transfermarkt | scraping | Valor de plantilla (calidad), plantilla por jugador (bajas) |
| Footystats | scraping | Córners, tarjetas, xG por selección |
| OpenWeatherMap | API key | Clima por estadio |

Bloqueadas por anti-bot (no se evaden): **Sofascore, FBref**.

### 2.2 Base de datos (SQLite, `data/bot.db`)

Esquema en [src/db/schema.sql](src/db/schema.sql). Tablas:

- **equipos**: tabla maestra de las 48 selecciones. Clave canónica `fifa_code` (3 letras) + IDs de cada fuente (`api_football_id`, `football_data_id`, `transfermarkt_id`, `sofascore_id`, `fbref_id`) y nombres (`odds_api_name`, `eloratings_name`, ...). Features: `elo`, `valor_plantilla`, `corners_favor`, `tarjetas_partido`, `xg_fs`, `xga_fs`, `fuerza_ataque`, `fuerza_defensa`.
- **partidos**: fixtures del Mundial (local, visita, grupo, fase, estado), enlazados por `football_data_id`.
- **resultados**: marcadores de los partidos jugados.
- **standings**: tabla de cada grupo (puntos, dg, gf).
- **cuotas**: 1X2 de Pinnacle por partido.
- **historico**: ~1900 partidos de selección 2022-24 (goles), base para estimar fuerzas.
- **apuestas**: log de apuestas con cuota, stake, EV, CLV, resultado.
- **jugadores**, **predicciones**: reservadas/auxiliares.

### 2.3 Mapeo entre fuentes

Cada fuente nombra distinto a las selecciones (Czechia/Czech Republic, IR Iran/Iran, Türkiye/Turkiye). La tabla maestra de referencia [data/referencia/equipos_mundial2026.csv](data/referencia/equipos_mundial2026.csv) cruza todas por `fifa_code`. El cruce se hace por nombre normalizado (sin acentos/minúsculas) con `OVERRIDES` para los casos difíciles.

---

## 3. Estructura del código

### 3.1 Infraestructura (`src/`)

- **config.py**: carga `.env` y define rutas (`db_path`, `cache_dir`, `data_dir`).
- **db/database.py**: conexión SQLite (`row_factory`, FK) e `init_db` (ejecuta `schema.sql`).
- **db/schema.sql**: definición de todas las tablas.

### 3.2 Clientes de API (`src/clients/`)

- **base.py** — `CachedClient`: HTTP con **caché en disco** (TTL configurable), **rate limit** (intervalo mínimo entre requests) y reintentos con backoff que respeta `Retry-After` (429).
- **api_football.py** — `ApiFootball`: `status`, `fixtures`, `teams`, `head_to_head`, `injuries`. Intervalo 6.5s (límite por minuto del plan free).
- **odds_api.py** — `OddsApi`: `sports`, `odds` (1X2 y outright; omite `bookmakers` si vacío para traer todas las casas).
- **football_data.py** — `FootballData`: `competition`, `standings`, `matches`, `equipo` (plantilla convocada).
- **weather.py** — `Weather`: pronóstico por coordenadas.

### 3.3 Scrapers (`src/scrapers/`)

- **eloratings.py** — `EloRatings`: descarga `en.teams.tsv` y `World.tsv`, devuelve `(código, nombre, elo, alias)`.
- **transfermarkt.py** — `Transfermarkt`: `participantes` (48 selecciones → verein_id + valor total desde la página del Mundial), `valores`, `kader` (plantilla por jugador con nombre, posición, valor).
- **footystats.py** — `Footystats`: `stats` (tabla del Mundial → por selección: xG, xGA, córners, tarjetas).

Todos cachean el HTML/TSV con TTL (24h) y usan User-Agent de navegador. Si una fuente devolviera un bloqueo duro (Cloudflare/captcha), el flujo se detiene; no se evade.

### 3.4 Ingesta (`src/`)

- **mapeo.py**: `EquipoMapeo` (dataclass), carga/guarda el CSV maestro, `upsert_db` (idempotente por `fifa_code`), `resolver` (búsqueda inversa desde cualquier fuente).
- **ingesta.py**: `ingestar_partidos`, `ingestar_resultados`, `ingestar_standings`, `ingestar_cuotas`. Normaliza el nombre de grupo entre endpoints (`_grupo`) y enlaza Odds↔football-data por par de equipos.
- **historico.py**: `ingestar_historico` (fixtures de selección 2022-24 de varias ligas/temporadas).

### 3.5 Modelo (`src/modelo/`)

- **dixon_coles.py** — núcleo estadístico. `ParametrosModelo`, `Ajustes` (multiplicadores ataque/defensa), `lambdas` (Elo→λ), `matriz_marcadores` (Poisson bivariado con corrección Dixon-Coles τ/ρ para marcadores bajos), `mercados` (de la matriz → 1X2, O/U, BTTS de forma consistente).
- **fuerzas.py** — el núcleo actual. Estima por **máxima verosimilitud ponderada en el tiempo** (vida media 1.5 años) las fuerzas ataque/defensa de cada selección sobre los 1900 partidos, **ancladas al Elo** (término θ·ΔElo) y con regularización ridge. `lambdas_desde_fuerzas` combina: fuerzas + θ_elo·ΔElo + θ_valor·Δlog(valor) + θ_xg·Δ(xG−xGA). `mapa_elo` cruza el histórico con eloratings.
- **parametros.py** — `tasa_base_torneo`, carga/persistencia de `ParametrosModelo`; `HOSTS` (anfitriones).
- **calibracion.py** — calibración de `beta_elo` (modelo Elo puro, legacy) contra el no-vig de Pinnacle por cross-entropy.
- **valor.py** — `sin_vig` (quita el margen), `ev`, `kelly` (fraccional con tope), `corregir_empate`, `mezclar_1x2` (shrinkage modelo↔mercado).
- **evaluacion.py** — `rps` (Ranked Probability Score, métrica correcta para 1X2), `prob_fuerzas`, `estrato` (clasifica por dificultad fácil/medio/reñido).
- **secundarios.py** — `over_under` (Poisson) para córners y tarjetas.
- **bet_builder.py** — `PREDICADOS` (1, X, 2, over/under, btts...) y `prob_conjunta` (suma las celdas de la matriz que cumplen todas las condiciones → captura la correlación intra-partido).
- **torneo.py** — simulación Monte Carlo: `cargar_estado` (standings + fixtures restantes), `simular` (grupos con desempates → 8 mejores terceros → eliminatorias). Cuadro de eliminatorias = sorteo aleatorio (aproximación documentada).

### 3.6 Salidas (`src/`)

- **reporte.py** — `analizar_1x2` (centraliza todo el análisis de un partido: fuerzas o fallback Elo, corrección de empate, shrinkage, guardarraíl, córners/tarjetas), `contexto_partido` (grupo + standings), `nivel_confianza`, `generar_markdown`.
- **apuestas.py** — `registrar` (apuesta con Kelly/EV), `actualizar` (captura cierre, calcula CLV y resultado), `resumen` (CLV medio, ROI).

---

## 4. El modelo paso a paso

1. **Fuerzas base**: de los 1900 partidos de selección 2022-24, se estiman ataque/defensa por equipo con Dixon-Coles ponderado en el tiempo. Problema: muestra pequeña y poca conexión entre confederaciones.
2. **Anclaje al Elo** (θ_elo): el Elo de eloratings, conectado globalmente, aporta la escala entre confederaciones que a las fuerzas les falta.
3. **Valor de plantilla** (θ_valor, calibrado al mercado): corrige el sesgo de calendario (ej. Colombia con buen Elo pero plantilla modesta; Irán infravalorado vs Bélgica). Baja el MAE vs Pinnacle de 11.7 a 10.0pp.
4. **xG de selección** (θ_xg): calibrado al mercado dio **0** — arrastra el mismo sesgo de calendario que las fuerzas, no aporta. El modelo lo descarta solo.
5. **De λ a mercados**: `matriz_marcadores` genera la matriz de resultados; de ahí salen 1X2/O-U/BTTS consistentes.
6. **Corrección de empate**: el modelo sobreestima empates ~3pp vs Pinnacle; se corrige anclando a la divergencia con el mercado (no a resultados de muestra pequeña, que daban ruido).
7. **Shrinkage** (w≈0.65): la "línea de trabajo" mezcla modelo y no-vig de Pinnacle; sobre ella se calcula el EV.
8. **Guardarraíl**: si modelo y mercado divergen >18pp, se marca poco fiable y **no se reporta EV**.
9. **Ajustes prospectivos (bajas)**: con input explícito de jugadores ausentes, se reduce el ataque (baja ofensiva) o se aumenta la permisividad defensiva (baja defensiva), ponderado por el valor del jugador.

---

## 5. Scripts (puntos de entrada, `scripts/`)

### Puesta en marcha / carga inicial
- **init_db.py** — crea `data/bot.db`.
- **validar_apis.py** — comprueba conectividad y cuotas de las 4 APIs con key.
- **cargar_mapeo.py** — carga las 48 selecciones del CSV a la DB.
- **verificar_mapeo.py** — contrasta el CSV contra The Odds API.
- **enriquecer_mapeo.py** — añade `football_data_id` al mapeo.
- **ingestar_elo.py** — Elo de las 48 (eloratings).
- **ingestar_valor.py** — valor de plantilla + `transfermarkt_id` (Transfermarkt).
- **ingestar_stats.py** — córners/tarjetas/xG (Footystats).
- **ingestar_historico.py** — ~1900 partidos de selección 2022-24 (API-Football).
- **estimar_fuerzas.py** — estima las fuerzas Dixon-Coles ancladas al Elo.
- **calibrar_sesgo.py** — corrección de empate + shrinkage.
- **calibrar_valor.py** / **calibrar_xg.py** — pesos de valor de plantilla y xG (calibrados al mercado).
- **calibrar_modelo.py** — calibración del modelo Elo puro (legacy).

### Uso diario
- **actualizar.py** — refresca partidos, resultados, standings y cuotas del Mundial.
- **generar_reporte.py** `LOCAL VISITA` — reporte pre-partido completo (markdown + snapshot JSON en `data/partidos/`).
- **analizar_partido.py** `LOCAL VISITA` — análisis rápido en consola.
- **bet_builder.py** `PARTIDO:mercado ... @cuota` — combinada con probabilidad por correlación vs naive.
- **simular_torneo.py** `[N]` — P(avanza)/P(campeón) vs mercado outright.
- **bajas.py** `FIFA` — detecta ausencias (plantilla TM vs convocados football-data).
- **impacto_bajas.py** `LOCAL VISITA "fuera_local" "fuera_visita"` — re-analiza descontando bajas.
- **registrar_apuesta.py** `LOCAL VISITA SEL CUOTA [STAKE]` — registra una apuesta.
- **clv.py** — actualiza cierre/CLV/resultados y muestra el historial.

### Evaluación
- **evaluar_modelo.py** — RPS out-of-sample, estratificado por dificultad, y divergencia vs Pinnacle.

---

## 6. Sesgos conocidos y métricas

**Sesgos** (documentados, no ocultados):
1. **Inter-confederación / calendario**: selecciones que dominan confederaciones débiles salen sobrevaloradas en goles. Mitigado por Elo + valor de plantilla; no eliminado.
2. **Techo vs mercado**: el modelo no bate a Pinnacle (MAE ~10pp). Su valor real está en partidos bien conectados y en el contexto cualitativo (bajas), no en outrights.
3. **RPS agregado engaña**: gran parte de la métrica viene de partidos fáciles → obligatorio estratificar por dificultad.

**Métricas de éxito** (las correctas, no el ROI de corto plazo):
- **CLV (Closing Line Value)**: ¿las cuotas tomadas baten la línea de cierre? Mejor predictor de habilidad a largo plazo.
- **RPS** out-of-sample estratificado.
- **MAE/cross-entropy** vs el no-vig de Pinnacle.

---

## 7. Orden de ejecución resumido

```
init_db → cargar_mapeo → actualizar → ingestar_elo → ingestar_valor → ingestar_stats
→ ingestar_historico → estimar_fuerzas → calibrar_sesgo → calibrar_valor → calibrar_xg
```
Día a día: `actualizar` → `generar_reporte` → (apostar en Betano) → `registrar_apuesta` → `clv`.

---

*Herramienta de análisis, no garantía de ganancia. El fútbol tiene varianza irreducible.*
