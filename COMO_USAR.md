# Cómo usar Botano

Guía rápida y directa. No necesitas saber programar: todo se maneja desde un menú.

---

## La forma más fácil (recomendada): doble clic

1. **Una sola vez:** doble clic en **`instalar.bat`** (prepara todo; tarda un par de minutos).
2. **Para usarlo**, elige una:
   - **`interfaz.bat`** → abre la **versión visual** en tu navegador (menús desplegables, tablas con color, gráficos). **Recomendada.**
   - **`iniciar.bat`** → abre el **menú de texto** en una ventana, si prefieres algo ligero.

Eso es todo. Si esto te funciona, puedes ignorar el resto del documento.

> La interfaz visual se abre sola en el navegador. Para cerrarla, cierra la ventana negra que se quedó abierta.

> Antes del primer `instalar.bat`, pega tus claves en el archivo `.env` (ver "Paso 1" más abajo, el punto de las claves).

---

## Alternativa por terminal (si prefieres)

1. **Una sola vez:** preparar el programa (instalar y descargar datos).
2. **Cada vez que quieras analizar:** ejecutar el menú con `python bot.py`.

---

## Paso 1 — Preparación (solo la primera vez)

Abre una terminal en la carpeta del proyecto y ejecuta, una por una:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

> **Si usas PowerShell** y `.venv\Scripts\activate` da un error de permisos, ejecuta primero esto (una vez) y vuelve a activar:
> ```
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> .venv\Scripts\Activate.ps1
> ```
> Sabrás que está activado porque la línea empieza con `(.venv)`. **Todos los comandos siguientes deben ejecutarse con `(.venv)` visible.**

Luego abre el archivo `.env` con el Bloc de notas y pega tus claves (gratuitas) entre los `=` y el final de cada línea:

```
API_FOOTBALL_KEY=tu_clave
ODDS_API_KEY=tu_clave
OPENWEATHER_KEY=tu_clave
FOOTBALL_DATA_KEY=tu_clave
```

> Dónde sacarlas (gratis): API-Football → dashboard.api-football.com · The Odds API → the-odds-api.com · OpenWeather → openweathermap.org · football-data → football-data.org/client/register

Finalmente, descarga y prepara todos los datos con **un solo comando**:

```
python setup.py
```

Esto tarda un par de minutos (descarga selecciones, Elo, valores, histórico y entrena el modelo). Al terminar, ya está listo.

---

## Paso 2 — Usar el bot (siempre)

```
python bot.py
```

Aparece un menú. Escribe el número de lo que quieras y pulsa Enter:

| Opción | Para qué sirve |
|---|---|
| **1. Actualizar datos** | Baja las cuotas, resultados y tabla más recientes. Hazlo antes de analizar el día del partido. |
| **2. Analizar un partido** | Escribes los dos equipos y te da el reporte completo: probabilidades, comparación con el mercado, valor (EV), córners y tarjetas. |
| **3. Analizar descontando bajas** | Igual que el 2, pero indicando jugadores lesionados/ausentes para ajustar el pronóstico. |
| **4. Evaluar una combinada** | Le pasas tu combinada y te dice la probabilidad real (teniendo en cuenta la correlación) y si tiene valor. |
| **5. Ver bajas de un equipo** | Lista los jugadores valiosos que no están en la convocatoria. |
| **6. Registrar una apuesta** | Apuntas una apuesta que hiciste en Betano para hacerle seguimiento. |
| **7. Ver historial y CLV** | Muestra tus apuestas y si batiste la línea de cierre (la señal de que vas bien). |
| **8. Ver códigos de equipos** | La lista de códigos de 3 letras (ARG, BRA, FRA...) que se usan al escribir los equipos. |
| **9. Ayuda / glosario** | Qué significa cada término (Elo, xG, EV, Over...). |
| **0. Salir** | Cierra el programa. |

> Los equipos se escriben con su **código de 3 letras** (opción 8 para verlos). Ejemplo: Argentina = `ARG`, Francia = `FRA`.

---

## Ejemplo de un día de partido

1. `python bot.py`
2. Opción **1** (actualizar datos).
3. Opción **2**, escribes `ARG` y `AUT` → lees el reporte.
4. Si decides apostar en Betano, opción **6** para registrarla.
5. Días después, opción **7** para ver tu CLV.

---

## Qué tener claro

- **No es una bola de cristal.** Es una herramienta de análisis; el fútbol tiene azar.
- Si el reporte dice **"EV no válido / el modelo diverge del mercado"**, significa que ahí el modelo no es fiable: no apuestes por esa diferencia.
- La mejor señal de que el sistema te ayuda no es ganar una semana, sino el **CLV positivo** (opción 7) a lo largo del torneo.
- Para entender cómo funciona por dentro: [documentacion.md](documentacion.md).
