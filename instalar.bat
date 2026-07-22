@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo ============================================
echo   Instalacion de Botano (Mundial 2026)
echo ============================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv
)
echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if not exist ".env" (
  echo Creando .env a partir de .env.example...
  copy /y ".env.example" ".env" >nul
  echo.
  echo IMPORTANTE: abre .env con el Bloc de notas y pega tus claves de API
  echo antes de refrescar datos desde la interfaz.
)
echo.
echo ============================================
echo   Listo. La base de datos ya viene cargada con el Mundial 2026.
echo   Para usar el bot: doble clic en interfaz.bat
echo   (dentro, el boton "Refrescar datos" trae partidos y cuotas al dia)
echo ============================================
pause
