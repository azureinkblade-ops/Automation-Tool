#!/usr/bin/env bash
# One-shot launcher: sleep until 18:00 local time, then exec the azink_main LoRA trainer.
# Uses the bundled Python to compute the wait (reliable on MSYS; `date -d` is unreliable here).
set -u
REPO="/c/Users/David/Documents/Automation tool"
cd "$REPO" || exit 1
PY="/c/Users/David/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"

# Compute seconds until next 18:00 via Python (cross-platform reliable)
wait=$("$PY" -c "
import time, datetime
now = datetime.datetime.now()
target = now.replace(hour=18, minute=0, second=0, microsecond=0)
if target <= now:
    target = target + datetime.timedelta(days=1)
print(int((target - now).total_seconds()))
")
echo "[launcher] sleeping ${wait}s until 18:00 then launching azink_main trainer"

# Sleep in 300s chunks (background-safe, no giant single sleep)
while [ "$wait" -gt 0 ]; do
  chunk=$(( wait > 300 ? 300 : wait ))
  sleep "$chunk"
  wait=$(( wait - chunk ))
done

echo "[launcher] starting trainer now"
exec env -u PYTHONPATH -u PYTHONHOME "$PY" tools/lora_training/train_xl_lora_folder.py \
  --pretrained_model models/sdxl-base \
  --train_data_dir lora-training/main-posts/datasets/train-1024 \
  --output_dir loras/main-posts \
  --resolution 1024 --train_batch_size 1 --gradient_accumulation_steps 4 \
  --learning_rate 0.0001 --num_train_epochs 4 --rank 16 --seed 42 \
  --mixed_precision bf16 --repeats 4 \
  > loras/main-posts/train-main-posts.log 2>&1
echo "TRAIN_DONE rc=$?" >> loras/main-posts/train-main-posts.log
