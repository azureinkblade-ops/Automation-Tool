@echo off
setlocal
cd /d "%~dp0"

echo Creating dedicated GPU environment (.venv-gpu) for local Stable Diffusion...
echo This isolates torch/diffusers from the app's main (Codex) Python.
echo.

if exist ".venv-gpu\Scripts\python.exe" (
    echo .venv-gpu already exists. Reusing it.
) else (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv .venv-gpu
)
if not exist ".venv-gpu\Scripts\python.exe" (
    echo Failed to create .venv-gpu. Aborting.
    pause
    exit /b 1
)

set "GPU_PY=.venv-gpu\Scripts\python.exe"

echo Upgrading pip in .venv-gpu...
"%GPU_PY%" -m pip install --upgrade pip

echo Installing CUDA-enabled PyTorch (CUDA runtime is bundled in the wheel; no separate CUDA Toolkit needed)...
"%GPU_PY%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

echo Installing diffusers stack...
"%GPU_PY%" -m pip install diffusers "transformers<5" "pillow<12.0,>=9.2.0" accelerate safetensors

echo.
echo Verifying CUDA access from .venv-gpu...
"%GPU_PY%" -c "import torch; print('torch', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'not detected')"

echo.
echo Saving LOCAL_SD_PYTHON to .env.local...
if not exist ".env.local" ( echo # Automation Tool local env > ".env.local" )
(findstr /c "LOCAL_SD_PYTHON=" ".env.local" >nul 2>&1) && (
    powershell -NoProfile -Command "(Get-Content '.env.local') -replace 'LOCAL_SD_PYTHON=.*', 'LOCAL_SD_PYTHON=%CD%\.venv-gpu\Scripts\python.exe' | Set-Content '.env.local'"
) || (
    echo LOCAL_SD_PYTHON=%CD%\.venv-gpu\Scripts\python.exe >> ".env.local"
)

echo.
echo Done. Restart the Automation Tool, then open Provider Strategy to verify local_stable_diffusion is ready (RTX 4080 SUPER).
pause
endlocal
