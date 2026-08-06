@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "ROOT=%CD%"
set "VENV=%ROOT%\.venv-win-build"
set "BRIDGE=%ROOT%\native_bridge\farever-atlas-bridge.exe"
set "BRIDGE_MSVC=%ROOT%\native_bridge\target\release\farever-atlas-bridge.exe"
set "BRIDGE_GNU=%ROOT%\native_bridge\target\x86_64-pc-windows-gnu\release\farever-atlas-bridge.exe"

if not exist "%BRIDGE%" (
    if exist "%BRIDGE_MSVC%" (
        copy /Y "%BRIDGE_MSVC%" "%BRIDGE%" >nul
    ) else if exist "%BRIDGE_GNU%" (
        copy /Y "%BRIDGE_GNU%" "%BRIDGE%" >nul
    ) else (
        echo Bridge binary missing. Build native_bridge first.
        exit /b 1
    )
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PY=py -3.12"
) else (
    set "PY=python"
)

%PY% -m venv "%VENV%"
if errorlevel 1 exit /b %errorlevel%

"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%

"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%\requirements.txt" pyinstaller
if errorlevel 1 exit /b %errorlevel%

echo Preparing UI fonts (Noto Sans)...
set "PYTHONPATH=%ROOT%\app"
"%VENV%\Scripts\python.exe" -m farever_atlas.fonts
if errorlevel 1 exit /b %errorlevel%

"%VENV%\Scripts\pyinstaller.exe" --noconfirm --clean ^
    --distpath "%ROOT%\dist" ^
    --workpath "%ROOT%\build\pyinstaller" ^
    "%ROOT%\packaging\windows\farever_atlas.spec"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Built: %ROOT%\dist\FareverAtlas.exe
exit /b 0
