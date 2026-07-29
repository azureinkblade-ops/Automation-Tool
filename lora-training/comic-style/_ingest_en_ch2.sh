#!/usr/bin/env bash
# Ingest EN Chapter 2 (Kael) faithful pages 007-014 into en_comic/.
# Verbatim-audited against en-2-chapter-2-first-hunt/chapter-text.txt.
set -euo pipefail
SRC="$HOME/AppData/Roaming/Hermes/composer-images"
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
EN="$BASE/en_comic"; mkdir -p "$EN"
add () { cp "$SRC/$1" "$EN/$2.png"; printf '%s\n' "$3" > "$EN/$2.txt"; echo "  + $2"; }

# 007 - Ch2 opening + mob-pattern diagram
add composer_2026-07-18_17-41-17-345_e79fbd.png en_comic_007_en_ch2_patterns \
"en_comic, vertical dark sci-fi manhwa page, deep blacks dark blues greys with cyan neon and red glow, header CHAPTER 2 — SHADOWFORGE INITIATION, Kael with dark topknot lunging with a long sword at a hulking shadow-wolf beast of swirling black tendrils and glowing red eyes in a rainy neon city, tactical diagram overlaying the beast breaking down attack patterns LUNGE LEFT LUNGE RIGHT FEINT SHOULDER BASH, cinematic webtoon"

# 008 - shoulder hit / critical blind
add composer_2026-07-18_17-41-17-362_0fec9b.png en_comic_008_en_ch2_blind \
"en_comic, vertical dark sci-fi manhwa page, high-contrast blacks dark blues neon cyan red, Kael with dark topknot lunging through blue digital rain toward a massive shadow tendril beast with red eyes, cyan HEALTH 91% UI, feint-left snap-right tactical arrows, critical red UI BLIND INFLICTED 6 SECONDS, 'Six seconds is all I need', intricate grittiness"

# 009 - third lunge / slow enough
add composer_2026-07-18_17-41-17-341_1fdd63.png en_comic_009_en_ch2_third_lunge \
"en_comic, vertical monochrome cyberpunk manhwa page, deep blacks dark blues stark white cyan highlights, Kael with dark ponytail lunging with a katana dodging a shadow tendril creature with red eyes, cyan HEALTH 91% then 62% UI bars, determined focused expression, 'Slow enough', digital void forest with blue code lines"

# 010 - beast defeated / loot / key
add composer_2026-07-18_17-41-17-363_00518e.png en_comic_010_en_ch2_loot \
"en_comic, vertical dark cyber-fantasy manhwa page, deep blues blacks greys gold white highlights, Kael in glowing blue circuitry coat lunging at a root-vine shadow beast with red eyes in rainy digital forest, cyan HEALTH 62% UI, golden starburst strike, red NIGHTSHADE BEAST DEFEATED box, loot screen SPIRIT BEAST HIDE NIGHTSHADE FANG UMBRAL QI FRAGMENT, quest LEGACY PATH SHADOWFORGE INITIATION"

# 011 - Shadow Anvil / trial start
add composer_2026-07-18_17-41-17-348_48ece1.png en_comic_011_en_ch2_anvil \
"en_comic, vertical dark fantasy-sci-fi manhwa page, deep blacks dark blues neon cyan, Kael with dark topknot and bandaged arm holding a jagged dark crystalline shard before a rainy cityscape with vine-like roots, holographic INTERACT WITH SHADOW ANVIL YES NO, 'You seek the path of the Shadowforge', gothic cathedral behind, red TRIAL START SHADOW CONSTRUCTS DESTROYED 0/10"

# 012 - trial constructs 1/10 -> 5/10
add composer_2026-07-18_17-41-17-366_f54020.png en_comic_012_en_ch2_trial_early \
"en_comic, vertical dark cyber-fantasy manhwa page, deep blues blacks with gold white magic highlights, Kael with dark topknot thrusting a glowing golden dagger into a faceless shadow humanoid in a digital rain void, red SHADOW CONSTRUCTS DESTROYED 1/10 WEAPON EMPOWERMENT +1, motion-blur multi-stage attack at 5/10 'The dagger grew stronger with every kill', 'Keep one between me and the other'"

# 013 - trial complete / Shadowforger class
add composer_2026-07-18_17-41-17-363_5e1dbd.png en_comic_013_en_ch2_trial_complete \
"en_comic, vertical dark fantasy-sci-fi manhwa page, near-black with gold light and cyan grid pixels, Kael in black tactical gear crouched holding a glowing golden sword facing a hulking shadow construct with a golden chest core, red SHADOW CONSTRUCTS DESTROYED 8/10 then 9/10 'One knee. One opening.', warm gold trial-complete screen TRIAL COMPLETE LEGACY CLASS GRANTED SHADOWFORGER PASSIVE UMBRAL QI MANIPULATION WEAPON SHADOWFORGED DAGGER"

# 014 - global announcement / round two / END CH2
add composer_2026-07-18_17-41-17-370_ce1ea1.png en_comic_014_en_ch2_end \
"en_comic, vertical cyberpunk-fantasy manhwa page, deep blues blacks greys gold, Kael with dark topknot and forearm bandage in layered clothing with chains before a cyan GLOBAL ANNOUNCEMENT hologram PLAYER KAELVEYRA HAS UNLOCKED THE FIRST LEGACY CLASS SHADOWFORGER, whispers from IronClaw Seraphine ArenValis, 'Round two. Let's make it count', red END OF CHAPTER 2 box"

echo "=== en_comic ==="; echo "png: $(ls "$EN"/*.png|wc -l)  txt: $(ls "$EN"/*.txt|wc -l)"
echo DONE