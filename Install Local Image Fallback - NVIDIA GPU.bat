@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

echo Installing local Stable Diffusion image fallback for NVIDIA GPUs...
echo This installs CUDA-enabled PyTorch first, then the image generation libraries.
echo.

"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
"%PYTHON_EXE%" -m pip install diffusers "transformers<5" "pillow<12.0,>=9.2.0" accelerate safetensors

echo.
echo Verifying CUDA access...
"%PYTHON_EXE%" -c "import torch; print('torch', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'not detected')"

echo.
echo Done. Restart the Automation Tool, then open Provider Strategy to verify local_stable_diffusion is ready.
pause
