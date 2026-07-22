# Desplegar Botano en la web (acceso solo tú, desde cualquier dispositivo)

Objetivo: usar Botano desde el navegador del móvil, tablet o cualquier PC, sin depender de tu Windows.
Plataforma: **Streamlit Community Cloud** (gratis). OCR en la nube: **Google Vision** (gratis hasta 1.000 imágenes/mes).

El código ya está preparado: en Windows sigue usando winocr; en la nube usa Google Vision automáticamente si están las credenciales.

---

## 1. Subir el proyecto a GitHub (ya hecho)

El repo ya está en GitHub e incluye la base de datos `data/bot.db`. Cuando actualices datos en local
(`python -m scripts.actualizar`, `estimar_fuerzas`, etc.), recuerda **commitear y subir `data/bot.db`**
para que la versión web se actualice.

## 2. Obtener una clave de OCR.space (gratis, sin tarjeta)

Para leer las capturas en la nube usamos **OCR.space** (gratis, sin tarjeta de crédito):

1. Entra en https://ocr.space/ocrapi/freekey
2. Pon tu correo y recibes una **API key gratis** (25.000 imágenes/mes, sin tarjeta).
3. La usarás en el paso 4 como `OCR_SPACE_API_KEY`.

Alternativa sin ninguna clave: en la app puedes **pegar el texto** de la captura (lo copias con el OCR
de tu propio móvil) en el recuadro de texto, y el bot lo procesa igual. No necesita OCR en el servidor.

## 3. Desplegar en Streamlit Cloud

1. Entra en https://share.streamlit.io/ con tu cuenta de GitHub.
2. **New app** → elige tu repositorio → rama `main` → archivo principal `app.py` → **Deploy**.
3. La primera vez tarda unos minutos en instalar dependencias.

## 4. Configurar los secretos (claves)

En la app desplegada: **menú (⋮) → Settings → Secrets**. Pega esto (formato TOML), rellenando tus valores:

```toml
API_FOOTBALL_KEY = "tu_clave"
ODDS_API_KEY = "tu_clave"
OPENWEATHER_KEY = "tu_clave"
FOOTBALL_DATA_KEY = "tu_clave"
OCR_SPACE_API_KEY = "tu_clave_del_paso_2"
```

Guarda; la app se reinicia y leerá las capturas con OCR.space. (Si prefieres no usar clave, pega el texto a mano.)

## 5. Restringir el acceso a solo ti

En **Settings → Sharing**, pon la app como privada e invita únicamente tu correo (o tu cuenta de Google).
Así solo tú entras, aunque la URL sea pública.

---

## Notas

- **Actualizar datos**: el botón **Refrescar datos** de la barra lateral trae partidos, resultados y cuotas
  en vivo (football-data.org, The Odds API) sin redesplegar. Para renovar el resto del modelo (fuerzas,
  eventos del Mundial), el workflow diario de GitHub Actions ya lo hace y sube `data/bot.db` al repo;
  Streamlit Cloud redespliega solo.
- **OCR**: en la nube, si no configuras `OCR_SPACE_API_KEY`, la subida de imagen fallará (winocr solo
  existe en Windows) — pero siempre puedes **pegar el texto** a mano. En tu PC local sigue con winocr sin tocar nada.
- **Cuota de Google Vision**: 1.000 imágenes/mes gratis. Uso personal no se acerca a ese límite.
