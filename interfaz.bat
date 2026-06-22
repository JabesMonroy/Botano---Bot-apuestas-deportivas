@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Abriendo Botano en tu navegador...
".venv\Scripts\python.exe" -m streamlit run app.py
pause
