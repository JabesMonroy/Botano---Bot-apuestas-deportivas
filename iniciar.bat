@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No encuentro el entorno virtual. Ejecuta primero instalar.bat.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" bot.py
pause
