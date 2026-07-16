@echo off
setlocal
set "APP_DIR=%~dp0"
set "BUNDLED_PY=C:\Users\jason\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" "%APP_DIR%gui.py"
  exit /b %ERRORLEVEL%
)

py -3 "%APP_DIR%gui.py"
if %ERRORLEVEL% EQU 0 exit /b 0

python "%APP_DIR%gui.py"
