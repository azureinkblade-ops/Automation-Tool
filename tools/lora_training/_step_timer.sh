#!/usr/bin/env bash
# Background step-timer: watches train.log for [step N] lines and records the
# wall-clock time of each, so we can compute per-step duration off-band.
LOG="loras/main-posts/train.log"
OUT="loras/main-posts/_step_times.log"
last_seen=""
for i in $(seq 1 600); do  # up to ~10 min
  cur=$(tr -d '\r' < "$LOG" 2>/dev/null | grep -E "\[step" | tail -1)
  if [ -n "$cur" ] && [ "$cur" != "$last_seen" ]; then
    ts=$(date +%s)
    echo "$ts  $cur" >> "$OUT"
    last_seen="$cur"
  fi
  sleep 1
done
echo "timer done" >> "$OUT"
