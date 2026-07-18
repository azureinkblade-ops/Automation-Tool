#!/usr/bin/env bash
# Detached, self-healing, RESUMABLE main-posts LoRA training wrapper.
# Launched via PowerShell Start-Process so it survives the agent session.
#
# Resume/manifest (Option B, 2026-07-18):
#  - GPU pre-flight via check_gpu.py (fails fast if VRAM busy).
#  - Dataset-prep stage runs once (CPU-only); skipped if already done
#    (recorded in the progress manifest).
#  - Training auto-resumes from the latest checkpoint (--resume_from_checkpoint latest).
#  - Progress manifest (<output>/training_manifest.json) tracks stage, latest
#    checkpoint, global step, completed epochs, timestamps, status, last error.
#  - On crash/interrupt: retries up to MAX_RETRIES, resuming from the latest
#    checkpoint each time. Stops on [done] or MAX_RETRIES.
#  - Writes PID to train.pid; logs to train.log.
#
# SAFETY: this wrapper never touches the live app server or the Hermes runtime.
# It only manages the LoRA training process and its own GPU/pid files.
set -u
cd "$(dirname "$0")/../.."   # repo root
GPY="$(pwd)/.venv-gpu/Scripts/python.exe"
TRAINER="tools/lora_training/train_xl_lora_folder.py"
PREP="tools/lora_training/prepare_main_posts_dataset.py"
CHK="tools/lora_training/check_gpu.py"
OUT="loras/main-posts"
LOG="$OUT/train.log"
PIDF="$OUT/train.pid"
MANIFEST="$OUT/training_manifest.json"
DATASET_DIR="lora-training/main-posts/datasets/train-1024"
MIN_FREE_GIB=12   # require >=12 GiB free VRAM before launching

mkdir -p "$OUT"
echo $$ > "$PIDF"

# --- GPU pre-flight ---
gpu_json="$("$GPY" "$CHK" "$MIN_FREE_GIB" 2>/dev/null)" || gpu_json='{"ok":false}'
gpu_ok="$(printf '%s' "$gpu_json" | "$GPY" -c 'import sys,json;print(json.load(sys.stdin).get("ok",False))' 2>/dev/null)"
if [ "$gpu_ok" != "True" ]; then
  echo "===== GPU PRE-FLIGHT FAILED @ $(date) =====" >> "$LOG"
  echo "  $gpu_json" >> "$LOG"
  echo "GPU not ready (need >=${MIN_FREE_GIB}GiB free). Aborting launch." >> "$LOG"
  rm -f "$PIDF"
  exit 3
fi
echo "===== GPU OK @ $(date): $gpu_json =====" >> "$LOG"

# --- Dataset-prep stage (CPU-only, skippable) ---
prep_done() {
  # Done if manifest says so AND the dataset dir has at least one image+txt pair.
  m="$([ -f "$MANIFEST" ] && cat "$MANIFEST" || echo '{}')"
  flagged="$(printf '%s' "$m" | "$GPY" -c 'import sys,json;print(json.load(sys.stdin).get("dataset_prep_done",False))' 2>/dev/null)"
  has_pairs=0
  if [ -d "$DATASET_DIR" ]; then
    if find "$DATASET_DIR" -maxdepth 1 \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) | grep -q .; then
      has_pairs=1
    fi
  fi
  [ "$flagged" = "True" ] && [ "$has_pairs" = "1" ]
}

if prep_done; then
  echo "===== dataset-prep SKIPPED (already done) @ $(date) =====" >> "$LOG"
else
  echo "===== dataset-prep START @ $(date) =====" >> "$LOG"
  env -u PYTHONPATH -u PYTHONHOME "$GPY" "$PREP" >> "$LOG" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "===== dataset-prep FAILED rc=$rc @ $(date) =====" >> "$LOG"
    rm -f "$PIDF"
    exit 4
  fi
  # mark prep done in manifest
  "$GPY" - <<PY >> "$LOG" 2>&1
import json, os
p = "$MANIFEST"
d = json.load(open(p)) if os.path.exists(p) else {}
d["dataset_prep_done"] = True
d["stage"] = "training"
json.dump(d, open(p, "w"), indent=2, sort_keys=True)
print("dataset_prep_done marked in manifest")
PY
  echo "===== dataset-prep DONE @ $(date) =====" >> "$LOG"
fi

# --- Training (resumable) ---
MAX_RETRIES=8
RETRY=0
while true; do
  echo "===== TRAIN ATTEMPT $((RETRY+1)) @ $(date) =====" >> "$LOG"
  env -u PYTHONPATH -u PYTHONHOME "$GPY" "$TRAINER" \
    --pretrained_model models/sdxl-base \
    --train_data_dir lora-training/main-posts/datasets/train-1024 \
    --output_dir "$OUT" \
    --resolution 1024 --train_batch_size 1 --gradient_accumulation_steps 4 \
    --learning_rate 0.0001 --num_train_epochs 4 --rank 16 --seed 42 \
    --mixed_precision bf16 --repeats 4 \
    --resume_from_checkpoint latest \
    --checkpointing_steps 200 --checkpointing_epochs 1 \
    --manifest "$MANIFEST" >> "$LOG" 2>&1
  RC=$?
  echo "===== attempt ended rc=$RC @ $(date) =====" >> "$LOG"
  if grep -q "\[done\]" "$LOG"; then
    echo "TRAINING COMPLETE (saw [done]) @ $(date)" >> "$LOG"
    break
  fi
  # If the run failed mid-training (not a clean completion), resume from the
  # latest checkpoint on the next attempt. Retry cap prevents infinite loops.
  RETRY=$((RETRY+1))
  if [ "$RETRY" -gt "$MAX_RETRIES" ]; then
    echo "MAX_RETRIES exceeded @ $(date)" >> "$LOG"
    break
  fi
  echo "retry $RETRY in 30s..." >> "$LOG"
  sleep 30
done
echo "WRAPPER_EXIT @ $(date)" >> "$LOG"
rm -f "$PIDF"
