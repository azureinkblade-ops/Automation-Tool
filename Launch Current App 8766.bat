@echo off
cd /d "%~dp0"
set "AUTOMATION_TOOL_PORT=8766"
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
start "" chrome "http://127.0.0.1:8766/"
if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" app.py
) else (
  py app.py
)
pause
