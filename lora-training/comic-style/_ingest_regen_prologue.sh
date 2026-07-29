#!/usr/bin/env bash
# Ingest 9 regenerated HA-prologue manhwa pages into azink_comic training set (011-019)
# + assemble full ordered prologue (9 new + 10 kept originals) for review.
set -euo pipefail

DL="$HOME/Downloads"
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
APP="$BASE/approved"
CAP="$BASE/captions"
ASM="$BASE/prologue-assembly"
mkdir -p "$APP" "$CAP" "$ASM"

# --- Task A: regen source -> approved id + descriptive name + caption ---
# format: "src|||id_name|||caption"
declare -a ROWS=(
"Generated image 1.png|||azink_comic_011_apartment_shift|||azink_comic, vertical manhwa webtoon page, clean ink linework with screentone shading, muted navy palette, young man dark messy hair in cramped rundown rainy apartment at night, flickering ceiling bulb, tense pre-storm atmosphere, close-up sweating anxious face, expressive fatigue, cinematic webtoon composition"
"Generated image 2.png|||azink_comic_012_transparent_walls|||azink_comic, vertical manhwa webtoon page, clean ink linework, young man on bed as apartment walls turn transparent wireframe, layered vision of mountains storms ancient stone gates and seated robed figures beneath stars, desaturated indigo aura, dramatic reveal composition, expressive shock"
"Generated image 3.png|||azink_comic_013_system_initializing|||azink_comic, vertical manhwa webtoon page, clean ink linework, dark apartment, translucent pale blue rectangular system UI panel unfolding in air, sharp monospaced interface glow, young man terrified sweating face close-up, high contrast cool palette, cinematic sci-fantasy webtoon"
"Generated image 4.png|||azink_comic_014_denial_stumble|||azink_comic, vertical manhwa webtoon page, clean ink linework, young man stumbling and catching a desk edge, dizzy off-balance motion lines, glowing blue system panel following him, cluttered dim bedroom, muted desaturated palette, expressive fear and disbelief"
"Generated image 5.png|||azink_comic_015_sync_lines|||azink_comic, vertical manhwa webtoon page, clean ink linework, three stacked pale blue system UI panels with monospaced text, young man backed against cracked wall breathing ragged, rainy night city window, high contrast cool palette, tense webtoon composition"
"Generated image 6.png|||azink_comic_016_pain_knees|||azink_comic, vertical manhwa webtoon page, clean ink linework, young man clutching chest crying out as golden ember qi energy erupts from his heart, sweat flying, then collapsed on hands and knees on apartment floor, dramatic cinematic lighting, dynamic pain composition"
"Generated image 7.png|||azink_comic_017_ember_core|||azink_comic, vertical manhwa webtoon page, clean ink linework, tiny golden ember glowing between the young man's hands over his chest, then kneeling drained and sweating on wooden floor, pale blue system UI panel with monospaced text below, muted palette with warm gold and cyan accents"
"Generated image 8.png|||azink_comic_018_stats_screen|||azink_comic, vertical manhwa webtoon page, clean ink linework grayscale, young man kneeling on worn apartment floor staring blankly at a floating cyan octagonal stat interface, desaturated grimy room, expressive tired numb face, cool limited palette, cinematic system-genre composition"
"Generated image 9.png|||azink_comic_019_closing_pulse|||azink_comic, vertical manhwa webtoon splash page, clean ink linework, young man sitting cross-legged on apartment floor, hand pressed to chest with soft warm golden glow beneath, cracked rainy city window behind, calm quiet resolution mood, cool blue and warm gold contrast, cinematic webtoon"
)

echo "=== TASK A: ingest to approved ==="
for row in "${ROWS[@]}"; do
  IFS='|||' read -r src _ _ idname _ _ cap <<<"$row"
  # robust split
  src="${row%%|||*}"
  rest="${row#*|||}"
  idname="${rest%%|||*}"
  cap="${rest#*|||}"
  cp "$DL/$src" "$APP/$idname.png"
  printf '%s\n' "$cap" > "$CAP/$idname.txt"
  echo "  + $idname.png  (+caption)"
done

echo "=== TASK B: assemble ordered prologue ==="
# reading order: beat -> source. n## = page order.
# 01-04 world/kai setup (kept), 05 shift(new011), 06 transparent(new012 or kept25),
# then system+sync+pain+core+stats+closing.
declare -a ORDER=(
"01_WB_world_moved_on|||$DL/8045b43a-4b7b-459a-b561-c467a26aa003.png"
"02_WB_fragments_remained|||$DL/88499e99-30c6-4ba2-9362-381e3a7f385b.png"
"03_K_apartment_night|||$DL/1d06674f-812b-4ceb-825c-18cf3486e3f5.png"
"04_K_stopped_dreaming|||$DL/af6558dd-d055-4ac2-827d-555d1b678e93.png"
"05_S_the_shift|||$APP/azink_comic_011_apartment_shift.png"
"06_S_transparent_walls|||$APP/azink_comic_012_transparent_walls.png"
"07_S_vision_world|||$DL/dd41137f-5d1c-472b-a489-ee35d1b87a5a.png"
"08_SY_system_initializing|||$APP/azink_comic_013_system_initializing.png"
"09_SY_denial_stumble|||$APP/azink_comic_014_denial_stumble.png"
"10_SN_sync_lines|||$APP/azink_comic_015_sync_lines.png"
"11_SN_pain_knees|||$APP/azink_comic_016_pain_knees.png"
"12_C_ember_core|||$APP/azink_comic_017_ember_core.png"
"13_C_stats_screen|||$APP/azink_comic_018_stats_screen.png"
"14_R_lungs_stop_hurting|||$DL/5c305923-ba54-4f35-bb38-96ec3dcbcc64.png"
"15_R_closing_pulse|||$APP/azink_comic_019_closing_pulse.png"
)
i=0
for row in "${ORDER[@]}"; do
  name="${row%%|||*}"
  src="${row#*|||}"
  cp "$src" "$ASM/$name.png"
  echo "  page $name"
  i=$((i+1))
done
echo "assembled $i pages into prologue-assembly/"
echo "DONE"