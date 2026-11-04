@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo   Diecast Radar - prueba en el PC
echo ==========================================

rem Vale tanto dentro de la carpeta del proyecto como al lado del zip
if exist "%~dp0radar\__main__.py" (
  cd /d "%~dp0"
) else (
  if not exist "%~dp0diecast-radar\radar" (
    echo Descomprimiendo diecast-radar.zip ...
    powershell -NoProfile -Command "Expand-Archive -Force '%~dp0diecast-radar.zip' '%~dp0'"
  )
  cd /d "%~dp0diecast-radar"
)

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo No encuentro Python. Instalalo desde python.org marcando "Add python.exe to PATH" y vuelve a abrir este archivo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno de Python ...
  %PY% -m venv .venv
)
echo Instalando dependencias (la primera vez tarda un poco) ...
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt
if not exist config.yaml copy config.example.yaml config.yaml >nul

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo.
echo === 1/2  Probando todas las fuentes (no guarda nada, tarda 1-2 min) ===
.venv\Scripts\python -m radar check > prueba-fuentes.txt 2>&1
type prueba-fuentes.txt
echo.
echo (Resultado guardado en diecast-radar\prueba-fuentes.txt)
echo.
echo === 2/2  Arrancando el bot y el panel: http://localhost:8791 ===
echo Si Windows pregunta por el firewall, puedes darle a Cancelar: en el PC funciona igual.
echo Para pararlo, cierra esta ventana.
start "" cmd /c "timeout /t 8 >nul & start http://localhost:8791"
.venv\Scripts\python -m radar run > bot.log 2>&1
type bot.log
pause
