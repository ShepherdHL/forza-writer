@echo off
setlocal

rem Launches the forza-writer fontpack GUI (tools/gen_modelbin_gui.py).
rem Always runs from this file's own folder, so it works no matter where
rem it's double-clicked from or copied to (as long as it stays in the repo root).
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" tools\gen_modelbin_gui.py
    goto :eof
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\gen_modelbin_gui.py
    goto :eof
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw tools\gen_modelbin_gui.py
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python tools\gen_modelbin_gui.py
    goto :eof
)

echo Python was not found on PATH.
echo Install Python 3.10+ from https://www.python.org/downloads/ and make
echo sure "Add python.exe to PATH" is checked during setup, then try again.
pause
