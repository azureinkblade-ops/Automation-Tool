#!/usr/bin/env bash
# Watch for the latent cache to be written, then IMMEDIATELY kill the trainer
# so training does NOT start. The trainer writes .latent_cache.pt atomically at
# the end of FolderDataset precompute, then continues into training in the same
# process -- so we kill the moment the file appears.
CACHE="lora-training/main-posts/datasets/train-1024/.latent_cache.pt"
for i in $(seq 1 2400); do   # up to ~5h (2400 * 8s)
  if [ -f "$CACHE" ]; then
    # cache exists -> kill all trainer procs NOW before training progresses
    sleep 1
    for pid in $(wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null | tr -d '\r' | grep "train_xl_lora_folder.py" | grep -oE "[0-9]+ *$" | tr -d ' '); do
      taskkill /PID "$pid" /F >/dev/null 2>&1
    done
    sz=$(stat -c '%s' "$CACHE" 2>/dev/null)
    echo "CACHE_WRITTEN_AND_TRAINER_KILLED @ $(date) cache_bytes=$sz"
    exit 0
  fi
  sleep 8
done
echo "CACHE_KILL_WATCHER_TIMEOUT @ $(date)"
