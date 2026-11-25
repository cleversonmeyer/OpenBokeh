@echo off
chcp 65001 >nul
pushd "%~dp0"
if not exist venv\Scripts\python.exe (echo Rode instalar.bat primeiro & pause & exit /b 1)
venv\Scripts\python openbokeh.py %*
popd
if errorlevel 1 pause
