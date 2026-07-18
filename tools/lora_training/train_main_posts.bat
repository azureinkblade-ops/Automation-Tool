@echo off
setlocal
cd /d "%~dp0\.."
set "PYTHONPATH="
set "PYTHONHOME="
set "GPY=%CD%\.venv-gpu\Scripts\python.exe%"
set "TRAINER=%CD%\tools\lora_training\train_xl_lora_folder.py"
set "PREP=%CD%\tools\lora_training\prepare_main_posts_dataset.py"
set "CHK=%CD%\tools\lora_training\check_gpu.py"
set "OUT=%CD%\loras\main-posts"
set "LOG=%OUT%\train.log"
set "PIDF=%OUT%\train.pid"
set "MANIFEST=%OUT%\training_manifest.json"
set "DATASET_DIR=%CD%\lora-training\main-posts\datasets\train-1024"
set "MIN_FREE_GIB=12"

if not exist "%OUT%" mkdir "%OUT%"
echo %PID% > "%PIDF%"

REM --- GPU pre-flight ---
"%GPY%" "%CHK%" %MIN_FREE_GIB% > "%OUT%\gpu_check.json" 2>&1
if errorlevel 1 (
  echo ===== GPU PRE-FLIGHT FAILED @ %DATE% %TIME% ===== >> "%LOG%"
  type "%OUT%\gpu_check.json" >> "%LOG%"
  echo GPU not ready (need ^>=%MIN_FREE_GIB%GiB free). Aborting launch. >> "%LOG%"
  del /f "%PIDF%" >nul 2>&1
  exit /b 3
)
echo ===== GPU OK @ %DATE% %TIME% ===== >> "%LOG%"

REM --- Dataset-prep stage (CPU-only, skippable) ---
set "PREP_DONE=0"
if exist "%MANIFEST%" (
  for /f %%i in ('%GPY% -c "import json,os;print(json.load(open(r'%MANIFEST%')).get('dataset_prep_done',False))" 2^>nul') do set "PREP_DONE=%%i"
)
REM also require the dataset dir to actually have images
set "HAS_PAIRS=0"
if exist "%DATASET_DIR%" (
  dir /b "%DATASET_DIR%\*.png" "%DATASET_DIR%\*.jpg" "%DATASET_DIR%\*.jpeg" >nul 2>&1 && set "HAS_PAIRS=1"
)
if "%PREP_DONE%"=="True" if "%HAS_PAIRS%"=="1" (
  echo ===== dataset-prep SKIPPED (already done) @ %DATE% %TIME% ===== >> "%LOG%"
) else (
  echo ===== dataset-prep START @ %DATE% %TIME% ===== >> "%LOG%"
  "%GPY%" "%PREP%" >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo ===== dataset-prep FAILED @ %DATE% %TIME% ===== >> "%LOG%"
    del /f "%PIDF%" >nul 2>&1
    exit /b 4
  )
  %GPY% -c "import json,os;p=r'%MANIFEST%';d=json.load(open(p)) if os.path.exists(p) else {};d['dataset_prep_done']=True;d['stage']='training';json.dump(d,open(p,'w'),indent=2,sort_keys=True)" >> "%LOG%" 2>&1
  echo ===== dataset-prep DONE @ %DATE% %TIME% ===== >> "%LOG%"
)

REM --- Training (resumable) ---
set MAX_RETRIES=8
set RETRY=0

:loop
echo ===== TRAIN ATTEMPT %RETRY% @ %DATE% %TIME% ===== >> "%LOG%"
"%GPY%" "%TRAINER%" ^
  --pretrained_model models/sdxl-base ^
  --train_data_dir lora-training/main-posts/datasets/train-1024 ^
  --output_dir "%OUT%" ^
  --resolution 1024 --train_batch_size 1 --gradient_accumulation_steps 4 ^
  --learning_rate 0.0001 --num_train_epochs 4 --rank 16 --seed 42 ^
  --mixed_precision bf16 --repeats 4 ^
  --resume_from_checkpoint latest ^
  --checkpointing_steps 200 --checkpointing_epochs 1 ^
  --manifest "%MANIFEST%" >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== attempt ended rc=%RC% @ %DATE% %TIME% ===== >> "%LOG%"

findstr /C:"[done]" "%LOG%" >nul
if %ERRORLEVEL%==0 (
  echo TRAINING COMPLETE @ %DATE% %TIME% >> "%LOG%"
  goto :done
)

set /a RETRY+=1
if %RETRY% GTR %MAX_RETRIES% (
  echo MAX_RETRIES exceeded @ %DATE% %TIME% >> "%LOG%"
  goto :done
)
echo retry %RETRY% in 30s... >> "%LOG%"
timeout /t 30 >nul
goto :loop

:done
echo WRAPPER_EXIT @ %DATE% %TIME% >> "%LOG%"
del /f "%PIDF%" >nul 2>&1
