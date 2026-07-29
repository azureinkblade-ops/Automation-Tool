#!/usr/bin/env bash
# Silent watcher: alerts (echo) only when the main-posts training finishes ([done])
# or the trainer dies. Otherwise stays quiet. Runs up to ~10h.
LOG="loras/main-posts/train.log"
for i in $(seq 1 1200); do  # 1200 * 30s = 10h
  if [ -f "$LOG" ] && grep -q "\[done\]" "$LOG" 2>/dev/null; then
    echo "TRAINING_DONE @ $(date)"
    break
  fi
  # trainer died without [done]?
  alive=$(wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null | grep -c "train_xl_lora_folder.py")
  if [ "$alive" -eq 0 ]; then
    # give it a moment in case of a brief restart window, then declare dead
    sleep 30
    alive2=$(wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null | grep -c "train_xl_lora_folder.py")
    if [ "$alive2" -eq 0 ]; then
      echo "TRAINER_GONE_NO_DONE @ $(date)"
      break
    fi
  fi
  sleep 30
done
echo "WATCHER_EXIT @ $(date)"
