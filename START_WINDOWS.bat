@echo off
setlocal
cd /d "%~dp0"

set "BRIDGE=%~dp0native_bridge\farever-atlas-bridge.exe"
if not exist "%BRIDGE%" (
    echo Bridge binary missing: %BRIDGE%
    exit /b 1
)

taskkill /IM farever-atlas-bridge.exe /F >nul 2>nul
start "Farever Atlas Bridge" /min "%BRIDGE%" --output "%~dp0native_bridge\farever-telemetry.json" --watch-ms 100
call "%~dp0run.bat" %*
exit /b %errorlevel%
