# Desplegar Botano en la web (acceso solo tú, desde cualquier dispositivo)

Objetivo: usar Botano desde el navegador del móvil, tablet o cualquier PC, sin depender de tu Windows.
Plataforma: **Streamlit Community Cloud** (gratis). OCR en la nube: **Google Vision** (gratis hasta 1.000 imágenes/mes).

El código ya está preparado: en Windows sigue usando winocr; en la nube usa Google Vision automáticamente si están las credenciales.

---

## 1. Subir el proyecto a GitHub (ya hecho)

El repo ya está en GitHub e incluye la base de datos `data/bot.db`. Cuando actualices datos en local
(`python -m scripts.actualizar`, `estimar_fuerzas`, etc.), recuerda **commitear y subir `data/bot.db`**
para que la versión web se actualice.

## 2. Crear las credenciales de Google Vision (gratis)

1. Entra en https://console.cloud.google.com/ y crea un proyecto (p. ej. "botano").
2. Busca **Cloud Vision API** y pulsa **Habilitar**.
3. Ve a **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**.
4. Crea la cuenta (rol "Visor" basta). Entra en ella → pestaña **Claves → Agregar clave → JSON**.
5. Se descarga un archivo `.json`. Lo necesitarás en el paso 4 (es gratis dentro de las 1.000 imágenes/mes).

## 3. Desplegar en Streamlit Cloud

1. Entra en https://share.streamlit.io/ con tu cuenta de GitHub.
2. **New app** → elige tu repositorio → rama `main` → archivo principal `app.py` → **Deploy**.
3. La primera vez tarda unos minutos en instalar dependencias.

## 4. Configurar los secretos (claves)

En la app desplegada: **menú (⋮) → Settings → Secrets**. Pega esto (en formato TOML), rellenando tus valores:

```toml
API_FOOTBALL_KEY = "tu_clave"
ODDS_API_KEY = "tu_clave"
OPENWEATHER_KEY = "tu_clave"
FOOTBALL_DATA_KEY = "tu_clave"

GOOGLE_VISION_CREDENTIALS = '''
{
  "type": "service_account",
  "project_id": "...",
  ...pega aquí TODO el contenido del .json del paso 2...
}
'''
```

Guarda. La app se reinicia y ya leerá las capturas con Google Vision.

## 5. Restringir el acceso a solo ti

En **Settings → Sharing**, pon la app como privada e invita únicamente tu correo (o tu cuenta de Google).
Así solo tú entras, aunque la URL sea pública.

---

## Notas

- **Actualizar datos**: la web usa la `data/bot.db` del repo. Para refrescarla, corre los scripts en tu PC,
  haz commit de `data/bot.db` y súbelo; Streamlit Cloud redespliega solo.
- **Ranking de valor**: en la nube el disco es efímero, así que el ranking se vacía si la app se reinicia
  (tras varios días inactiva). Es lo acordado; lo rehaces pegando capturas.
- **OCR**: si no configuras `GOOGLE_VISION_CREDENTIALS`, en la nube el lector de capturas fallará
  (winocr solo existe en Windows). En tu PC local sigue funcionando sin tocar nada.
- **Cuota de Google Vision**: 1.000 imágenes/mes gratis. Uso personal no se acerca a ese límite.
