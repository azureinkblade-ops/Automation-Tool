#!/usr/bin/env bash
# Ingest 14 faithful HA Chapter-1 manhwa pages into azink_comic training set (020-033).
# Excludes: THUD-knockdown reject, garbled 40-panel strip, montage-overview composite.
set -euo pipefail
SRC="$HOME/AppData/Roaming/Hermes/composer-images"
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
APP="$BASE/approved"; CAP="$BASE/captions"
mkdir -p "$APP" "$CAP"

ingest () { # $1=srcfile $2=idname $3=caption
  cp "$SRC/$1" "$APP/$2.png"
  printf '%s\n' "$3" > "$CAP/$2.txt"
  echo "  + $2"
}

ingest composer_2026-07-16_21-11-35-641_585b56.png azink_comic_020_ch1_stats_screen \
"azink_comic, vertical manhwa webtoon page, clean ink linework, sleepless young man dark messy hair sitting against bed frame in cluttered rainy apartment at night, hand pressed to chest, pale blue system status interface panel with monospaced stats text, muted noir palette, expressive exhaustion, cinematic webtoon composition"

ingest composer_2026-07-16_21-11-35-641_f483dc.png azink_comic_021_ch1_denial_mirror \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man splashing water at a cracked grimy bathroom mirror then lying awake in dark bedroom, faint blue system panel glow on the wall, cool desaturated palette, quiet insomniac mood, expressive tired face"

ingest composer_2026-07-16_21-11-35-640_fcc298.png azink_comic_022_ch1_morning_from_floor \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man sitting on apartment floor by rain-streaked window at dawn, overdue bill and pill bottles on the counter, close-up sweating pained face, hand clutching chest, muted grey blue palette, somber slice-of-life webtoon"

ingest composer_2026-07-16_21-11-35-640_c028d9.png azink_comic_023_ch1_rent_alarm \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man in bed looking at phone reading 6:15 low battery, then sitting on bed edge tying sneakers in small rundown apartment, barred window rainy night, caption boxes, muted palette, weary resigned mood"

ingest composer_2026-07-16_21-11-35-682_e0baaf.png azink_comic_024_ch1_daily_task \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man staring at two floating pale blue system panels showing a daily task list with objectives and requirements, cluttered apartment kitchenette, close-up intense sweating face, cool limited palette, system-genre composition"

ingest composer_2026-07-16_21-11-35-682_0e2aa2.png azink_comic_025_ch1_stairwell_lobby \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man unlocking apartment door 506 then walking down industrial stairwell to a rainy building lobby, pale blue system panel glow, mailboxes, muted noir palette, quiet commute mood, expressive fatigue"

ingest composer_2026-07-16_21-11-35-641_a3647d.png azink_comic_026_ch1_city_qi_sense \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man walking a rainy neon city street unnoticed by crowd, golden qi energy threads swirling around his chest, extreme close-up alarmed face, pale blue perception system panel, cool palette with warm gold accent, cinematic urban webtoon"

ingest composer_2026-07-16_21-11-35-683_f889c9.png azink_comic_027_ch1_store_marta \
"azink_comic, vertical manhwa webtoon page, clean ink linework, tired young man in blue uniform entering a dim convenience store talking with a female coworker behind the counter, rainy glass door, speech bubbles, muted blue grey palette, quiet slice-of-life webtoon composition"

ingest composer_2026-07-16_21-11-35-683_190691.png azink_comic_028_ch1_morning_rush \
"azink_comic, vertical manhwa webtoon page, clean ink linework, busy convenience store morning rush then young man crouching with a stock box in the back room, pale blue breathing-cycle system panels, close-up chest with glowing golden qi energy, muted palette, cinematic system-genre webtoon"

ingest composer_2026-07-16_21-11-35-641_e6a298.png azink_comic_029_ch1_alley_meeting \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man carrying recycle boxes in a wet neon back alley at night meeting a calm man in a long dark coat, faint golden qi glow leaking from the box, tense confrontation, speech bubbles, muted noir palette, cinematic webtoon"

ingest composer_2026-07-16_21-11-35-669_d1c5f6.png azink_comic_030_ch1_pressure_endure \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man buckling under invisible spiritual pressure against a brick alley wall, hand braced on wall, pale blue emergency task system panel with a countdown, lit convenience store visible through a doorway, sweat and strain, muted noir palette, tense webtoon composition"

ingest composer_2026-07-16_21-11-35-669_0787b3.png azink_comic_031_ch1_who_taught_you \
"azink_comic, vertical manhwa webtoon page, clean ink linework, young man kneeling against a recycle dumpster in a rainy alley clutching his glowing golden chest while a tall man in a black trench coat watches calmly, blue system countdown numerals, task-complete system panel, muted noir palette, dramatic webtoon"

ingest composer_2026-07-16_21-11-35-669_5684a7.png azink_comic_032_ch1_card_azure_hall \
"azink_comic, vertical manhwa webtoon page, clean ink linework, tall man in black trench coat and exhausted young man in a rainy alley, a small dark card on the wet ground engraved AZURE MERIDIAN HALL NORTH HOLLOW, faint golden chest glow, speech bubbles, muted noir palette, cinematic webtoon composition"

ingest composer_2026-07-16_21-11-35-669_563320.png azink_comic_033_ch1_standing \
"azink_comic, vertical manhwa webtoon page, clean ink linework, rainy crowded city street as the coated man vanishes into the crowd, young man crouching with phone then standing in the alley holding a small glowing golden ember, pale blue new-objective system panel, muted noir palette, resolute closing mood"

echo "=== approved total ==="; ls "$APP"/*.png | wc -l
echo "DONE"