@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "FAREVER_BOOTSTRAP=py -3"
) else (
    set "FAREVER_BOOTSTRAP=python"
)

%FAREVER_BOOTSTRAP% -m venv .venv
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

echo.
echo Setup complete. Start Farever Standalone with:
echo   run.bat
