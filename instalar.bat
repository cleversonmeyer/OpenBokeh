@echo off
chcp 65001 >nul
pushd "%~dp0"
echo === OpenBokeh - instalacao ===
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version || (echo Instale o Python 3.10+ em python.org & pause & exit /b 1)
if not exist venv %PY% -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Pronto! Agora rode iniciar.bat
popd
pause
