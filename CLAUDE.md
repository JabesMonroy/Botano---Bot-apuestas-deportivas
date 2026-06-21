# CLAUDE.md

Guía operativa para Claude Code en este proyecto: bot de análisis cuantitativo de apuestas (Mundial 2026). El plan, fuentes y reglas de razonamiento viven en `prompt_maestro_agente_mundial2026.md`.

## Idioma
- Respuestas, análisis y mensajes de commit en español, con ortografía y tildes correctas.

## Estilo de respuesta
- Preciso y breve. Sin relleno, sin repetir la pregunta, sin resúmenes innecesarios.
- Tono serio y técnico. Sin entusiasmo artificial ni emojis.
- Conclusión o recomendación primero; el detalle solo si aporta.
- No explicar el código que escribo salvo que se pida: el código habla por sí mismo.
- Ahorrar tokens: ir al grano, no listar opciones que no voy a tomar.
- Si falta un dato o una fuente no alcanza, decirlo. No inventar.

## Código
- Limpio, eficiente e idiomático; consistente con los patrones del repo.
- **Sin comentarios en el código** salvo que se pida explícitamente.
- Nombres descriptivos; funciones cortas con una sola responsabilidad.
- Tipado estático donde el lenguaje lo permita (type hints en Python).
- Manejo explícito de errores y de límites de rate de las APIs; cachear según TTL.
- Sin claves ni secretos en el código: usar `.env` / variables de entorno.
- Sin código muerto, prints de depuración ni TODOs sin resolver.
- Verificar antes de declarar terminado: ejecutar o probar lo que cambié y reportar el resultado real.

## Git / GitHub
- Registrar cambios con commits atómicos y mensaje claro en español: `tipo: qué cambió` (ej. `feat: cliente The Odds API con manejo de rate limit`).
- **No añadir `Co-Authored-By: Claude` ni ninguna coautoría de Claude/Anthropic en los commits.**
- No hacer commit ni push salvo que se pida. Para cambios grandes, trabajar en rama, no en `main`.
- Nunca usar `--no-verify` ni saltar hooks.

## Datos y fuentes
- Respetar cuotas de API (API-Football 100 req/día): cachear de forma agresiva.
- No scraping agresivo ni evasión de anti-bot. Ante Cloudflare/captcha duro, frenar y avisar.
- No promediar fuentes en conflicto en silencio: señalar la discrepancia.
- Distinguir siempre probabilidad (del suceso) de valor (probabilidad vs cuota).

## Alcance
- Herramienta de análisis, no garantía de ganancia. No fomentar *chasing losses* ni subir stakes para recuperar.
