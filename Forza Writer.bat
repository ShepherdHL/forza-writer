@echo off
setlocal

rem Launches the Forza Writer shell (tools/gen_modelbin_web.py), a local
rem pywebview/WebView2 desktop app -- not a hosted web service.
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" tools\gen_modelbin_web.py
    goto :eof
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\gen_modelbin_web.py
    goto :eof
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw tools\gen_modelbin_web.py
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python tools\gen_modelbin_web.py
    goto :eof
)

echo Python was not found on PATH.
echo Install Python 3.10+ from https://www.python.org/downloads/ and make
echo sure "Add python.exe to PATH" is checked during setup, then try again.
pause
