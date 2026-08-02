@echo off
setlocal
cd /d "%~dp0"

set "FAREVER_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%FAREVER_PYTHON%" (
    echo Virtual environment missing. Run setup.bat first.
    exit /b 1
)

if not defined FAREVER_GAME_DIR if exist "%~dp0nyx_game_dir.conf" (
    set /p FAREVER_GAME_DIR=<"%~dp0nyx_game_dir.conf"
)

set "PYTHONPATH=%~dp0app;%PYTHONPATH%"
"%FAREVER_PYTHON%" -m farever_standalone %*
exit /b %errorlevel%
