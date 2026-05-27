@echo off
cd /d "%~dp0"
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "127.0.0.1:8765" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>nul
start "" chrome "http://127.0.0.1:8765/"
if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" app.py
) else (
  py app.py
)
pause
