#!/usr/bin/env bash
# Restructure azink_comic into per-novel comic tracks (2026-07-18).
# HA: 011-019, 034  -> ha_comic/001-010
# HP: 035-042       -> hp_comic/001-008
# EN / SF: empty folders created for future ingest.
set -euo pipefail
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
SRC="$BASE/approved"; SCAP="$BASE/captions"
HA="$BASE/ha_comic"; HP="$BASE/hp_comic"; EN="$BASE/en_comic"; SF="$BASE/sf_comic"
mkdir -p "$HA" "$HP" "$EN" "$SF"

# map old approved id -> (new folder, new num, novel tag)
move () { # $1=oldidprefix $2=destdir $3=newnum $4=noveltag
  local old img txt dest num tag
  old="$1"; dest="$2"; num=$(printf '%03d' "$3"); tag="$4"
  img=$(ls "$SRC"/${old}_*.png 2>/dev/null | head -1)
  [ -z "$img" ] && { echo "WARN no img for $old"; return; }
  txt=$(ls "$SCAP"/${old}_*.txt 2>/dev/null | head -1)
  cp "$img" "$dest/${tag}_comic_${num}.png"
  if [ -n "$txt" ]; then
    # rewrite caption: replace leading "azink_comic," with "<tag>_comic,"
    sed "s/^azink_comic,/${tag}_comic,/" "$txt" > "$dest/${tag}_comic_${num}.txt"
  fi
  echo "  $old -> ${tag}_comic_${num}"
}

# ---- HA (10) ----
move azink_comic_011 "$HA" 1 ha
move azink_comic_012 "$HA" 2 ha
move azink_comic_013 "$HA" 3 ha
move azink_comic_014 "$HA" 4 ha
move azink_comic_015 "$HA" 5 ha
move azink_comic_016 "$HA" 6 ha
move azink_comic_017 "$HA" 7 ha
move azink_comic_018 "$HA" 8 ha
move azink_comic_019 "$HA" 9 ha
move azink_comic_034 "$HA" 10 ha   # pressure-trigger (was 034)

# ---- HP (8) ----
move azink_comic_035 "$HP" 1 hp
move azink_comic_036 "$HP" 2 hp
move azink_comic_037 "$HP" 3 hp
move azink_comic_038 "$HP" 4 hp
move azink_comic_039 "$HP" 5 hp
move azink_comic_040 "$HP" 6 hp
move azink_comic_041 "$HP" 7 hp
move azink_comic_042 "$HP" 8 hp

echo "=== verify counts ==="
echo "ha_comic png: $(ls "$HA"/*.png 2>/dev/null|wc -l)  txt: $(ls "$HA"/*.txt 2>/dev/null|wc -l)"
echo "hp_comic png: $(ls "$HP"/*.png 2>/dev/null|wc -l)  txt: $(ls "$HP"/*.txt 2>/dev/null|wc -l)"
echo "=== remove old approved copies (keep rejected/ untouched) ==="
rm -f "$SRC"/azink_comic_0{11,12,13,14,15,16,17,18,19,34}_*.png "$SRC"/azink_comic_0{11,12,13,14,15,16,17,18,19,34}_*.txt
rm -f "$SRC"/azink_comic_0{35,36,37,38,39,40,41,42}_*.png "$SRC"/azink_comic_0{35,36,37,38,39,40,41,42}_*.txt
echo "approved/ leftover png: $(ls "$SRC"/*.png 2>/dev/null|wc -l)  (should be 0 of the moved ones; old 001-010 quarantined separately)"
echo "=== caption trigger check (first line each) ==="
head -1 "$HA"/ha_comic_001.txt; head -1 "$HP"/hp_comic_001.txt
echo "DONE"