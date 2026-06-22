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
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Preparando todos los datos (puede tardar un par de minutos)...
echo.
".venv\Scripts\python.exe" setup.py
echo.
echo ============================================
echo   Listo. Para usar el bot: doble clic en iniciar.bat
echo ============================================
pause
