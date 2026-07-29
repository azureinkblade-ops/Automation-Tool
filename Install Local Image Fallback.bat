@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

echo Installing local Stable Diffusion image fallback dependencies...
echo This can take several minutes because PyTorch is large.
"%PYTHON_EXE%" -m pip install -r requirements-local-image.txt

echo.
echo Done. Restart the Automation Tool, then open Provider Strategy to verify local_stable_diffusion is ready.
pause
