#!/usr/bin/env bash
# Self-healing launcher for the main-posts LoRA training.
# - Runs the cached trainer (latents+embeds precomputed once -> ~2s/step, NOT the 27h runaway).
# - Restarts on crash up to MAX_RETRIES, with a backoff.
# - Stops on clean completion ([done] line) or hard deadline.
# Usage: bash tools/lora_training/run_main_posts_watchdog.sh
set -u
cd "$(dirname "$0")/../.."   # repo root

GPY="$(pwd)/.venv-gpu/Scripts/python.exe"
TRAINER="tools/lora_training/train_xl_lora_folder.py"
LOG="loras/main-posts/train.log"
mkdir -p loras/main-posts

CMD=(env -u PYTHONPATH -u PYTHONHOME "$GPY" "$TRAINER" \
  --pretrained_model models/sdxl-base \
  --train_data_dir lora-training/main-posts/datasets/train-1024 \
  --output_dir loras/main-posts \
  --resolution 1024 --train_batch_size 1 --gradient_accumulation_steps 4 \
  --learning_rate 0.0001 --num_train_epochs 4 --rank 16 --seed 42 \
  --mixed_precision bf16 --repeats 4)

MAX_RETRIES=5
RETRY=0
DEADLINE=$(date -u -d "+9 hours" +%s 2>/dev/null || echo 9999999999)  # hard stop ~9h from now

while true; do
  echo "===== TRAIN ATTEMPT $((RETRY+1)) @ $(date) =====" >> "$LOG"
  "${CMD[@]}" >> "$LOG" 2>&1
  RC=$?
  echo "===== attempt ended rc=$RC @ $(date) =====" >> "$LOG"
  if grep -q "\[done\]" "$LOG"; then
    echo "TRAINING COMPLETE (saw [done])" >> "$LOG"
    break
  fi
  NOW=$(date -u +%s)
  if [ "$NOW" -ge "$DEADLINE" ]; then
    echo "DEADLINE reached, stopping watchdog." >> "$LOG"
    break
  fi
  RETRY=$((RETRY+1))
  if [ "$RETRY" -gt "$MAX_RETRIES" ]; then
    echo "MAX_RETRIES exceeded, stopping." >> "$LOG"
    break
  fi
  sleep 30
done
echo "WATCHDOG_EXIT" >> "$LOG"
