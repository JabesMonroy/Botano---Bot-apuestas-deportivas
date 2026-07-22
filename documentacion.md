# Documentación — Botano (Bot de análisis de apuestas, Mundial 2026)

Documento de referencia de toda la arquitectura: qué hace cada archivo, cómo fluyen los datos y por qué el modelo está construido así. Para el plan conceptual ver [prompt_maestro_agente_mundial2026.md](prompt_maestro_agente_mundial2026.md); para el runbook rápido ver [README.md](README.md).

---

## 1. Qué es y filosofía

Sistema cuantitativo que, para cada partido del Mundial 2026, estima probabilidades de 1X2, Over/Under, BTTS, córners, tarjetas y saques de meta, las compara con la línea *sharp* de Pinnacle y calcula valor esperado (EV). En eliminación directa modela prórroga y penales (mercado "para avanzar") y mide el desempeño real vía CLV. La simulación Monte Carlo del torneo se eliminó: para outrights el mercado es mejor estimador que el modelo (sesgo amplificado documentado).

Principios de diseño:

- **Honestidad sobre optimismo**: cada componente documenta sus sesgos en vez de esconderlos. Si el modelo diverge mucho del mercado, un **guardarraíl** lo marca como no fiable en vez de reportar un EV falso.
- **El mercado como referencia**: Pinnacle (la casa más afilada) es el ancla. Toda incorporación de datos (valor de plantilla, xG) se **calibra contra el mercado**; si no reduce la divergencia, se le da peso cero.
- **Transparencia**: modelo por capas explícitas (no caja negra), con parámetros auditables y persistidos en JSON.

---

## 2. Arquitectura de datos

### 2.1 Fuentes (9)

| Fuente | Acceso | Rol |
|---|---|---|
| The Odds API | API key | Cuotas de Pinnacle (1X2, totals y BTTS), calendario, outright del Mundial |
| football-data.org | API key | Resultados, standings, plantillas convocadas |
| eloratings.net | scraping (TSV) | Elo de selecciones (escala global entre confederaciones) |
| API-Football | API key (free) | Histórico de selección 2022-24 para estimar fuerzas |
| Transfermarkt | scraping | Valor de plantilla (calidad), plantilla por jugador (bajas) |
| Footystats | scraping | Córners, tarjetas, xG por selección (previos al Mundial) |
| wc2026-events (GitHub) | CSV públicos | Eventos por partido del Mundial 2026 (WhoScored): tiros con coordenadas, córners, tarjetas, saques de meta |
| StatsBomb Open Data | JSON públicos | Mundial 2022: calibra el xG por tiro y los parámetros de tiros/córners |
| OpenWeatherMap | API key | Clima por estadio |

Bloqueadas por anti-bot (no se evaden): **Sofascore, FBref**.

### 2.2 Base de datos (SQLite, `data/bot.db`)

Esquema en [src/db/schema.sql](src/db/schema.sql). Tablas:

- **equipos**: tabla maestra de las 48 selecciones. Clave canónica `fifa_code` (3 letras) + IDs de cada fuente (`api_football_id`, `football_data_id`, `transfermarkt_id`, `sofascore_id`, `fbref_id`) y nombres (`odds_api_name`, `eloratings_name`, ...). Features: `elo`, `valor_plantilla`, `corners_favor`, `tarjetas_partido`, `xg_fs`, `xga_fs`, `fuerza_ataque`, `fuerza_defensa`.
- **partidos**: fixtures del Mundial (local, visita, grupo, fase, estado), enlazados por `football_data_id`.
- **resultados**: marcadores de los partidos jugados.
- **standings**: tabla de cada grupo (puntos, dg, gf).
- **cuotas**: cuotas de Pinnacle por partido y mercado: `1X2` (selección = código FIFA o `X`), `totals` (selección = `over2.25`, `under2.5`, ... con la línea embebida) y `btts` (`si`/`no`). Los totals llegan en la misma llamada bulk (2 créditos de cuota); el BTTS requiere una llamada por evento y solo se pide para partidos a ≤4 días (cuota-consciente).
- **historico**: ~1900 partidos de selección 2022-24 (goles), base para estimar fuerzas.
- **estadisticas_mundial**: por partido del Mundial y equipo: goles a 90', xG propio, tiros, tiros al arco, córners, tarjetas, saques de meta (fuente wc2026-events).
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
- **wc_events.py** — `WcEvents`: baja los CSV de eventos del repo público wc2026-events (WhoScored), calcula por equipo y partido a 90': goles, xG propio por tiro, tiros (al arco), córners, tarjetas y saques de meta; cachea solo el resumen (no los CSV de ~2 MB).

Todos cachean el HTML/TSV con TTL (24h) y usan User-Agent de navegador. Si una fuente devolviera un bloqueo duro (Cloudflare/captcha), el flujo se detiene; no se evade.

### 3.4 Ingesta (`src/`)

- **mapeo.py**: `EquipoMapeo` (dataclass), carga/guarda el CSV maestro, `upsert_db` (idempotente por `fifa_code`), `resolver` (búsqueda inversa desde cualquier fuente).
- **ingesta.py**: `ingestar_partidos`, `ingestar_resultados`, `ingestar_standings`, `ingestar_cuotas`. Normaliza el nombre de grupo entre endpoints (`_grupo`) y enlaza Odds↔football-data por par de equipos.
- **historico.py**: `ingestar_historico` (fixtures de selección 2022-24 de varias ligas/temporadas).

### 3.5 Modelo (`src/modelo/`)

- **dixon_coles.py** — núcleo estadístico. `ParametrosModelo`, `Ajustes` (multiplicadores ataque/defensa), `lambdas` (Elo→λ), `matriz_marcadores` (Poisson bivariado con corrección Dixon-Coles τ/ρ para marcadores bajos), `corregir_empate_matriz` (deflacta la diagonal y renormaliza: la corrección de empate afecta a **todos** los mercados de forma coherente), `mercados` (de la matriz → 1X2, O/U, BTTS).
- **fuerzas.py** — el núcleo actual. Estima por **máxima verosimilitud ponderada en el tiempo** (vida media 1.5 años) las fuerzas ataque/defensa de cada selección sobre los ~1900 partidos, **ancladas al Elo** (término θ·ΔElo) y con regularización ridge. La ventaja local `gamma` solo se aplica a filas con localía real (los partidos del Mundial son neutrales salvo anfitriones). Los partidos del Mundial entran con **mezcla 0.7·xG + 0.3·goles** (menos ruido con 3-4 partidos por equipo). `lambdas_desde_fuerzas` combina: `mu + mu_torneo` + fuerzas + θ_elo·ΔElo + θ_valor·Δlog(valor) + θ_xg·Δ(xG−xGA). `mapa_elo` resuelve primero por la tabla `equipos` (evita fallos de cruce por nombre) y solo usa nombres para el resto del histórico.
- **xg.py** — xG por tiro: logístico sobre log(distancia), ángulo al arco y cabeza; penales fijos en 0.76. Calibrado con los 1430 tiros del Mundial 2022 (StatsBomb); correlación 0.81 por tiro con el xG completo de StatsBomb.
- **parametros.py** — `tasa_base_torneo`, carga/persistencia de `ParametrosModelo`; `HOSTS` (anfitriones).
- **calibracion.py** — calibración de `beta_elo` (modelo Elo puro, legacy) contra el no-vig de Pinnacle por cross-entropy.
- **valor.py** — `sin_vig` (quita el margen con el método **power**, que corrige el sesgo favorito-longshot del reparto proporcional), `ev`, `kelly` (fraccional con tope), `corregir_empate` (legacy, usado en calibración), `mezclar_1x2` (shrinkage modelo↔mercado).
- **evaluacion.py** — `rps` (Ranked Probability Score, métrica correcta para 1X2), `prob_fuerzas`, `estrato` (clasifica por dificultad fácil/medio/reñido).
- **secundarios.py** — `over_under` (Poisson) para córners y saques de meta; `over_under_nb` (binomial negativa) para tarjetas, con ratio varianza/media estimado de los partidos reales del Mundial.
- **bet_builder.py** — `PREDICADOS` (1, X, 2, over/under, btts...) y `prob_conjunta` (suma las celdas de la matriz que cumplen todas las condiciones → captura la correlación intra-partido).

### 3.6 Salidas (`src/`)

- **reporte.py** — `analizar_1x2` (centraliza todo el análisis de un partido: fuerzas o fallback Elo, corrección de empate en la matriz, shrinkage por estrato, guardarraíl, córners/tarjetas/saques de meta con mezcla Footystats↔Mundial real), `contexto_partido` (grupo + standings), `nivel_confianza`, `generar_markdown`.
- **apuestas.py** — `registrar` (apuesta con Kelly/EV), `actualizar` (captura cierre, calcula CLV y resultado), `resumen` (CLV medio, ROI).

---

## 4. El modelo paso a paso

1. **Fuerzas base**: de los ~1900 partidos de selección 2022-24 **más los partidos ya jugados del Mundial**, se estiman ataque/defensa por equipo con Dixon-Coles ponderado en el tiempo. La ventaja local solo aplica a partidos con localía real (el Mundial es neutral salvo anfitriones). Los partidos del Mundial entran como **0.7·xG + 0.3·goles** — con 3-4 partidos por equipo, los goles son ruido y el xG informa más.
2. **Anclaje al Elo** (θ_elo): el Elo de eloratings, conectado globalmente, aporta la escala entre confederaciones que a las fuerzas les falta. Se resuelve por la tabla maestra (`fifa_code`), no por nombre — un cruce por nombre dejó a Turquía, RD Congo y Cabo Verde con Elo medio durante la fase de grupos (bug corregido).
3. **Valor de plantilla** (θ_valor, calibrado al mercado): corrige el sesgo de calendario. MAE vs Pinnacle actual: **6.1pp** (7.8 sin valor).
4. **xG de selección de Footystats** (θ_xg): calibrado al mercado sigue dando **0** — arrastra el mismo sesgo de calendario. El xG que sí aporta es el **por tiro de los partidos reales del Mundial** (punto 1).
5. **Nivel de goles del torneo** (`mu_torneo`): este Mundial va a ~3.1 goles/partido frente a ~2.7 del histórico; un offset con shrinkage (k=40) sobre los partidos jugados corrige la subestimación del Over sin perseguir la racha (objetivo = mezcla xG/goles, no los goles brutos).
6. **De λ a mercados**: `matriz_marcadores` genera la matriz de resultados; la **corrección de empate se aplica a la matriz** (deflacta la diagonal y renormaliza), de modo que 1X2, O/U, BTTS, marcadores y bet builder son coherentes entre sí. El delta se ancla a la divergencia con el mercado (tras las demás correcciones quedó en ~0.008).
7. **Shrinkage** (w=0.65; **w=0.80 en partidos reñidos**, donde el modelo no demostró ventaja): la "línea de trabajo" mezcla modelo y no-vig de Pinnacle (devig **power**); sobre ella se calcula el EV.
8. **Ancla de mercado en goles**: la línea principal de totals y el BTTS de Pinnacle se comparan con el modelo con la misma mecánica (no-vig power → shrinkage con w=0.80 fijo → EV → guardarraíl de 18pp). Las **líneas asiáticas** (enteras y de cuarto, p. ej. 2.25) se valoran con su estructura real de pagos (push y medias apuestas), no como binarias.
9. **Guardarraíl**: si modelo y mercado divergen >18pp, se marca poco fiable y **no se reporta EV**.
10. **Eliminatorias**: el 1X2 es a 90'; para el mercado "avanza" se modela la prórroga con la misma matriz a λ/3 y, si persiste el empate, penales al 50/50 (antes se repartía el empate proporcional al favorito, que lo sobrevaloraba).
11. **Ajustes prospectivos (bajas)**: con input explícito de jugadores ausentes, se reduce el ataque (baja ofensiva) o se aumenta la permisividad defensiva (baja defensiva), ponderado por el valor del jugador.
12. **Secundarios**: córners y saques de meta con Poisson, tarjetas con binomial negativa (ratio varianza/media del torneo); promedios previos de Footystats mezclados con lo observado en el Mundial (peso n/(n+3) por partidos jugados).

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
- **calibrar_xg_disparo.py** — ajusta el xG por tiro (logístico) con StatsBomb WC22.
- **ingestar_eventos.py** — baja los eventos del Mundial 2026 (wc2026-events) y llena `estadisticas_mundial`; reporta discrepancias de marcador contra la DB en vez de taparlas.
- **estimar_fuerzas.py** — estima las fuerzas Dixon-Coles ancladas al Elo (con mezcla xG en partidos del Mundial) y el offset `mu_torneo`.
- **calibrar_sesgo.py** — corrección de empate + shrinkage.
- **calibrar_valor.py** / **calibrar_xg.py** — pesos de valor de plantilla y xG (calibrados al mercado).
- **calibrar_modelo.py** — calibración del modelo Elo puro (legacy).

### Uso diario
- **actualizar.py** — refresca partidos, resultados, standings y cuotas del Mundial.
- **generar_reporte.py** `LOCAL VISITA` — reporte pre-partido completo (markdown + snapshot JSON en `data/partidos/`).
- **analizar_partido.py** `LOCAL VISITA` — análisis rápido en consola (incluye saques de meta).
- **bet_builder.py** `PARTIDO:mercado ... @cuota` — combinada con probabilidad por correlación vs naive.
- **predecir_ko.py** `[FASE]` — cruces de eliminación directa: 1X2 a 90' + P(clasifica) con prórroga (λ/3) y penales 50/50.
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
2. **Techo vs mercado**: el modelo no bate a Pinnacle (MAE ~6pp tras las correcciones de julio 2026; antes ~10pp). Su valor real está en partidos bien conectados y en el contexto cualitativo (bajas), no en outrights.
3. **RPS agregado engaña**: gran parte de la métrica viene de partidos fáciles → obligatorio estratificar por dificultad. En reñidos el modelo no demostró ventaja → shrinkage reforzado (w=0.80).
4. **Finishing del Mundial por encima del xG** (3.09 goles vs 2.37 xG por partido): en gran parte varianza; `mu_torneo` apunta a la mezcla xG/goles, no a los goles brutos, para no extrapolar la racha.
5. **Motivación en la 3.ª fecha de grupos** (rotaciones con clasificación asegurada): no modelada; el mercado sí la recoge — el guardarraíl es la defensa.

**Métricas de éxito** (las correctas, no el ROI de corto plazo):
- **CLV (Closing Line Value)**: ¿las cuotas tomadas baten la línea de cierre? Mejor predictor de habilidad a largo plazo.
- **RPS** out-of-sample estratificado.
- **MAE/cross-entropy** vs el no-vig de Pinnacle.

---

## 7. Orden de ejecución resumido

```
init_db → cargar_mapeo → actualizar → ingestar_elo → ingestar_valor → ingestar_stats
→ ingestar_historico → calibrar_xg_disparo → ingestar_eventos
→ estimar_fuerzas → calibrar_valor → calibrar_xg → calibrar_sesgo
```
Día a día: `actualizar` → `ingestar_eventos` → `estimar_fuerzas` → `calibrar_sesgo` → `generar_reporte` / `predecir_ko` → (apostar en Betano) → `registrar_apuesta` → `clv`. El workflow diario de GitHub Actions ejecuta los cuatro primeros pasos automáticamente.

---

## 8. Expansión post-Mundial: 8 competiciones

Decidido en julio 2026: tras la final, el bot apunta a EPL, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, Brasileirão y Liga BetPlay (Colombia). Casa de ejecución: Betano; ancla sharp: Pinnacle donde existe; presupuesto: free tier. Ya integrado en la interfaz (selector "Competición" en Analizar partido, ordenado por fecha del próximo partido y con un panel de **fiabilidad** por competición — ver 8.3).

Un mismo club puede jugar dos competiciones a la vez (liga doméstica + Champions League): la tabla `equipos_competicion` (muchos-a-muchos) registra en cuáles participa cada equipo; `equipos.liga_id` solo guarda la liga "de origen" (la primera con la que se mapeó). El selector de equipos por competición filtra por `equipos_competicion`, no por `equipos.liga_id` — de lo contrario los clubes de Champions League "desaparecían" de su liga doméstica (bug real, corregido 21-jul-2026).

### 8.1 Backtest histórico (fundación)

Tablas `ligas` y `partidos_club` (esquema en [src/db/schema_clubes.sql](src/db/schema_clubes.sql)):

- [src/clients/football_data_uk.py](src/clients/football_data_uk.py) — CSVs históricos de football-data.co.uk (resultados, estadísticas de partido y cuotas de Pinnacle **apertura y cierre**: PSH/PSCH, líneas O/U 2.5 y hándicap asiático). El ISP colombiano bloquea el sitio (redirect a Coljuegos), así que el cliente intenta el sitio directo y cae a capturas de web.archive.org localizadas vía API CDX (elige la captura con más filas).
- [src/scrapers/understat.py](src/scrapers/understat.py) — xG por partido de Understat (endpoint JSON `getLeagueData/{liga}/{año}`), cacheado 24h. Cobertura: big-5 + RFPL desde 2014.
- [scripts/ingestar_ligas.py](scripts/ingestar_ligas.py) — carga 7 temporadas (2019-20 a 2025-26) × 5 ligas: 11.896 partidos, 99.7% con xG de Understat emparejado.
- [scripts/backtest_clubes.py](scripts/backtest_clubes.py): walk-forward (re-ajuste cada 28 días) contra tasas base, no-vig del **cierre** de Pinnacle y la apertura. EPL 2024-25+2025-26 (754 partidos OOS): RPS modelo con xG **0.2001** vs cierre Pinnacle **0.1975** (gap 0.0026); O/U 2.5 el modelo **empata** al cierre (0.2421 vs 0.2431). La mezcla 0.7·xG+0.3·goles mejora sobre solo-goles en las 5 ligas. Apostar contra la **apertura** simulada da CLV medio negativo (−4 a −7%): **sin valor sistemático contra Pinnacle** — la ventaja práctica está en la mezcla modelo↔mercado contra Betano y en secundarios.

### 8.2 Pipeline en vivo

- `src/ligas.py` — registro único de las 6 competiciones (codigo fd.co.uk, fd_org, odds_api, understat), usado por todos los scripts de esta sección.
- [scripts/cargar_mapeo_clubes.py](scripts/cargar_mapeo_clubes.py) — bootstrap de equipos por liga desde el calendario de football-data.org (no `teams()`, que incluye equipos históricos/inactivos): asigna `fifa_code` (tla, con desambiguación automática si dos ligas comparten sigla, p. ej. Brentford/Brest ambos "BRE"), cruza `odds_api_name` contra los eventos de The Odds API y `fd_uk_nombre` contra los nombres históricos de `partidos_club`, ambos por fuzzy match (`difflib`, umbral 0.62) con overrides puntuales para abreviaturas irreductibles (Inter/Internazionale, Paris SG/Paris Saint-Germain, M'gladbach, demonimos franceses Lyonnais/Brestois/Rennais). Reporta lo no cruzado explícitamente (recién ascendidos sin histórico, o sin cuota publicada aún).
- [scripts/actualizar_ligas.py](scripts/actualizar_ligas.py) — generaliza `src/ingesta.py` (ahora parametrizado por `codigo`/`liga_id`/`grupo_default`) para las 6 competiciones: partidos, resultados, standings (una tabla por liga, sin el bug de "Matchday"/"PHASE" que football-data.org devuelve como valor literal de `group` para ligas domésticas) y cuotas Pinnacle.
- [scripts/estimar_fuerzas_clubes.py](scripts/estimar_fuerzas_clubes.py) — combina `partidos_club` histórico (traducido a nombres canónicos vía `fd_uk_nombre`) con resultados en vivo de la temporada en curso, ajusta Dixon-Coles de clubes y persiste `data/modelos/fuerzas_club_{codigo}.json`. Exige mínimo 380 partidos (Champions League, con solo 189 de la temporada 25/26 ya cerrada, queda excluida hasta que la UEFA publique el calendario 26/27 — el objeto correcto no es forzar un ajuste con datos insuficientes).
- `src.reporte.analizar_club(conn, data_dir, liga_codigo, local, visita)` — mismo contrato `Analisis` que `analizar_1x2`, así que reutiliza `mostrar_analisis`, EV, guardarraíl y todos los mercados combinados sin duplicar la UI. Sin anclaje a Elo (dentro de una liga el grafo de enfrentamientos está completamente conectado, no hay problema inter-confederación) ni corrección de empate (rho ya la captura por liga). Córners/tarjetas esperados se calculan on-the-fly desde el promedio histórico de `partidos_club` por equipo.

**Limitaciones conocidas**: sin el ajuste de bajas (Transfermarkt no está mapeado a clubes); sin el bloque de estilo/planteamiento (exclusivo del Mundial); Champions League sin cuotas de Pinnacle todavía (The Odds API no lista el torneo hasta que se sortee la fase de liga); ~4 equipos por liga grande sin standings por retraso de football-data.org.

### 8.3 Brasileirão, Liga BetPlay y el sistema de fiabilidad

**Brasileirão** — mismas fuentes en vivo que las big-5 (football-data.org `BSA`, Odds API `soccer_brazil_campeonato`), pero el histórico viene del formato "extra" de football-data.co.uk (`new/BRA.csv`, un solo archivo con todas las temporadas 2012-2023): **solo resultados y cuota de apertura de Pinnacle, sin córners/tarjetas/tiros ni xG** (Understat no cubre Brasil). [src/clients/football_data_uk.py](src/clients/football_data_uk.py) tiene un segundo método (`extra`) para este formato; [scripts/ingestar_ligas.py](scripts/ingestar_ligas.py) lo detecta vía `Liga.fd_uk_extra`. La temporada 2026 en curso ya aporta resultados en vivo (182/380 partidos jugados a 21-jul).

**Liga BetPlay (Colombia)** — sin fuente gratuita de calendario en vivo: football-data.org y The Odds API no cubren Colombia, y el plan gratuito de API-Football solo da las temporadas 2022-2024 (no la actual — `{'plan': 'Free plans do not have access to this season'}`). [scripts/ingestar_betplay.py](scripts/ingestar_betplay.py) ingesta ese histórico (1256 partidos válidos, separando Apertura/Clausura por el campo `round` para no chocar con la restricción `UNIQUE(liga_id, temporada, local, visita)`) solo para tener fuerzas de referencia. Sin cuotas, sin xG, sin córners/tarjetas, **sin calendario automático**: el usuario elige los equipos a mano.

**Sistema de fiabilidad** ([src/ui/fiabilidad.py](src/ui/fiabilidad.py)): calcula un nivel (alta/media/baja/no disponible) por competición a partir de hechos verificables, no de un texto fijo — ¿existe `backtest_club_{codigo}.json` con RPS validado contra el cierre de Pinnacle?, ¿hay cuotas de mercado (`Liga.odds_api`)?, ¿hay xG real (`Liga.understat`)?, ¿hay calendario en vivo (`Liga.fd_org`)? Se muestra en un expander bajo el selector de competición. Resultado actual: **alta** (Mundial + las 5 big-5, con backtest walk-forward guardado en `data/modelos/backtest_club_{codigo}.json` vía [scripts/backtest_clubes.py](scripts/backtest_clubes.py)), **media** (Brasileirão: mercado y calendario sí, xG y backtest no), **baja** (Liga BetPlay: ni mercado ni calendario en vivo), **no disponible** (Champions League: menos de 380 partidos para ajustar).

---

*Herramienta de análisis, no garantía de ganancia. El fútbol tiene varianza irreducible.*
