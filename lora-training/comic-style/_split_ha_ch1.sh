#!/usr/bin/env bash
# Move remaining HA Ch1 (020-033) into ha_comic/ as 011-024.
set -euo pipefail
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
SRC="$BASE/approved"; SCAP="$BASE/captions"; HA="$BASE/ha_comic"
mkdir -p "$HA"
move () {
  local old="$1" num=$(printf '%03d' "$2") img txt
  img=$(ls "$SRC"/${old}_*.png 2>/dev/null|head -1); [ -z "$img" ] && { echo "WARN $old"; return; }
  txt=$(ls "$SCAP"/${old}_*.txt 2>/dev/null|head -1)
  cp "$img" "$HA/ha_comic_${num}.png"
  [ -n "$txt" ] && sed 's/^azink_comic,/ha_comic,/' "$txt" > "$HA/ha_comic_${num}.txt"
  echo "  $old -> ha_comic_${num}"
}
move azink_comic_020 11
move azink_comic_021 12
move azink_comic_022 13
move azink_comic_023 14
move azink_comic_024 15
move azink_comic_025 16
move azink_comic_026 17
move azink_comic_027 18
move azink_comic_028 19
move azink_comic_029 20
move azink_comic_030 21
move azink_comic_031 22
move azink_comic_032 23
move azink_comic_033 24
echo "=== ha_comic now: $(ls "$HA"/*.png|wc -l) png / $(ls "$HA"/*.txt|wc -l) txt ==="
rm -f "$SRC"/azink_comic_0{20,21,22,23,24,25,26,27,28,29,30,31,32,33}_*.png "$SRC"/azink_comic_0{20,21,22,23,24,25,26,27,28,29,30,31,32,33}_*.txt
echo "approved/ leftover: $(ls "$SRC"/*.png 2>/dev/null|wc -l) (expect 0)"
echo "=== trigger check ==="; head -1 "$HA"/ha_comic_011.txt
echo DONE