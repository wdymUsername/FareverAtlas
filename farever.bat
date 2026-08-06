@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "VENV_PYTHON=%ROOT%.venv\Scripts\python.exe"
set "BRIDGE=%ROOT%native_bridge\farever-atlas-bridge.exe"
set "TELEMETRY=%ROOT%native_bridge\farever-telemetry.json"
set "GAME_DIR_FILE=%ROOT%nyx_game_dir.conf"

if "%~1"=="" goto usage
set "COMMAND=%~1"
shift

if /I "%COMMAND%"=="setup" goto setup
if /I "%COMMAND%"=="start" goto start
if /I "%COMMAND%"=="stop" goto stop
if /I "%COMMAND%"=="restart" goto restart
if /I "%COMMAND%"=="help" goto usage
if /I "%COMMAND%"=="-h" goto usage
if /I "%COMMAND%"=="--help" goto usage

echo Unknown command: %COMMAND%
goto usage

:usage
echo Usage: farever.bat ^<command^> [args...]
echo.
echo Commands:
echo   setup              Create the Python venv and install dependencies
echo   start [args...]    Start the native bridge, then Farever Atlas
echo   stop               Stop Farever Atlas and the native bridge
echo   restart [args...]  Stop anything running, then start fresh
echo.
echo Atlas args ^(forwarded by start/restart^):
echo   --dev              Show a Reload button for soft in-process UI reloads
exit /b 1

:setup
where py >nul 2>nul
if %errorlevel% equ 0 (
    set "FAREVER_BOOTSTRAP=py -3"
) else (
    set "FAREVER_BOOTSTRAP=python"
)

%FAREVER_BOOTSTRAP% -m venv .venv
if errorlevel 1 exit /b %errorlevel%

"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%

"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

echo Preparing UI fonts (Noto Sans)...
set "PYTHONPATH=%ROOT%app"
"%VENV_PYTHON%" -m farever_atlas.fonts
if errorlevel 1 exit /b %errorlevel%

echo.
echo Setup complete. Start with:
echo   farever.bat start
exit /b 0

:stop
echo Stopping Farever Atlas...
taskkill /IM farever-atlas-bridge.exe /F >nul 2>nul
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw)\.exe$' -and $_.CommandLine -match 'farever_atlas' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul
echo Farever Atlas stopped.
exit /b 0

:restart
call "%~f0" stop
timeout /t 1 /nobreak >nul
call "%~f0" start %*
exit /b %errorlevel%

:start
if not exist "%VENV_PYTHON%" (
    echo Python environment missing. Run: farever.bat setup
    exit /b 1
)
if not exist "%BRIDGE%" (
    echo Bridge binary missing: %BRIDGE%
    echo Build it with: native_bridge\build.sh
    exit /b 1
)

taskkill /IM farever-atlas-bridge.exe /F >nul 2>nul

if not defined FAREVER_GAME_DIR if exist "%GAME_DIR_FILE%" (
    set /p FAREVER_GAME_DIR=<"%GAME_DIR_FILE%"
)

if not defined FAREVER_TELEMETRY_INTERVAL_MS set "FAREVER_TELEMETRY_INTERVAL_MS=100"

echo Starting native bridge...
powershell -NoProfile -Command "Start-Process -FilePath $env:BRIDGE -ArgumentList '--output',$env:TELEMETRY,'--watch-ms',$env:FAREVER_TELEMETRY_INTERVAL_MS -WorkingDirectory $env:ROOT -WindowStyle Hidden"

echo Starting Farever Atlas...
set "PYTHONPATH=%ROOT%app;%PYTHONPATH%"
"%VENV_PYTHON%" -m farever_atlas %*
exit /b %errorlevel%
