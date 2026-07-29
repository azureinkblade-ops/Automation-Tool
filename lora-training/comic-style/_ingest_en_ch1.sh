#!/usr/bin/env bash
# Ingest EN Chapter-1 (Kael) faithful pages 001-006 into en_comic/.
# Image 7 (Aren flashback) is held separately in en_comic_lore/ (NOT Ch1).
set -euo pipefail
SRC="$HOME/AppData/Roaming/Hermes/composer-images"
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
EN="$BASE/en_comic"; LORE="$BASE/en_comic_lore"
mkdir -p "$EN" "$LORE"

add () { # $1=src $2=id $3=caption
  cp "$SRC/$1" "$EN/$2.png"; printf '%s\n' "$3" > "$EN/$2.txt"; echo "  + $2"
}
lore () { # hold a non-Ch1 page as lore
  cp "$SRC/$1" "$LORE/$2.png"; printf '%s\n' "$3" > "$LORE/$2.txt"; echo "  (lore) + $2"
}

# 001 - The Great Reset
add composer_2026-07-18_15-24-17-287_470560.png en_comic_001_en_great_reset \
"en_comic, vertical sci-fi cyberpunk manhwa page, deep blue neon cyan palette, young man Kael with dark hair tied in bun standing before a floor-to-ceiling window of a futuristic cityscape at twilight, sleek black NexusPod with glowing blue glyphs beside him, holographic PATCH 12.0 Ascension Wars screen, chaotic forum overlays, cinematic webtoon"

# 002 - pod / spawn choice
add composer_2026-07-18_15-24-17-292_9c94a7.png en_comic_002_en_spawn_choice \
"en_comic, vertical sci-fi cyberpunk manhwa page, deep blue neon palette, Kael barefoot in a black tank top seated in a high-tech neural pod chair, glowing blue holo interface offering City of Beginnings versus Nightfall Hollow marked high danger with a red pentagram symbol, cybernetic port glowing at his temple, tense webtoon composition"

# 003 - arrive Nightfall Hollow
add composer_2026-07-18_15-24-17-301_2e7faf.png en_comic_003_en_nightfall_hollow \
"en_comic, vertical dark-fantasy sci-fi manhwa page, midnight blue charcoal and steel-grey with cyan glyphs and gold wireframe materialization around Kael, a dense twisted night forest with a circular stone portal, ruined pillars, 'System Message: Location Nightfall Hollow Region Twilight Vale', cinematic webtoon"

# 004 - Nightshade Beast
add composer_2026-07-18_15-24-17-301_ad05ba.png en_comic_004_en_nightshade_beast \
"en_comic, vertical dark sci-fi manhwa page, deep blues blacks greys with glowing cyan data-streams and red beast eyes, Kael seen from behind in a dark swampy forest holding a worn bronze sword, a massive shadow-wolf Nightshade Beast Level 5 with glowing red eyes emerging from mist, gold hexagonal Legacy Path Shadow Forging diagram, high-contrast webtoon"

# 005 - neural sync / login
add composer_2026-07-18_15-24-17-301_a71421.png en_comic_005_en_neural_sync \
"en_comic, vertical sci-fi manhwa page, neon blues and golds, Kael reclining in an egg-shaped neural pod against vertical streams of blue digital code, then a wireframe avatar in deep space wrapped in swirling golden energy lines, black armored suit overlaid with glowing golden circuitry, cinematic webtoon"

# 006 - first blow (climax)
add composer_2026-07-18_15-24-17-304_dccdfb.png en_comic_006_en_first_blow \
"en_comic, vertical dark sci-fi manhwa page, deep blues blacks greys, a shadow-wolf beast with glowing red eyes and bared teeth in ruined neon-lit city, Kael lunging with a drawn katana trailing a golden-white slash, rain and motion blur, 'Patch 12.0 didn't nerf you', dynamic action webtoon"

# 007 (HELD - NOT Ch1) - Aren flashback / lore
lore composer_2026-07-18_15-32-09-299_6a7a2e.png en_comic_lore_aren_betrayal \
"en_comic, vertical sci-fi fantasy manhwa page, neon blues glowing golds stark reds, Kael (silver-white hair, scar over left eye, black-white robe with red accents) standing in a red digital portal holding a golden sphere, opposite a younger man Aren Valis kneeling defeated as his chest bursts with golden energy, 'A year ago he stood one step from ascension', 'Aren wanted Kael's Core' — LORE / FLASHBACK, not Chapter 1"

echo "=== en_comic ==="; echo "png: $(ls "$EN"/*.png|wc -l)  txt: $(ls "$EN"/*.txt|wc -l)"
echo "=== en_comic_lore (held) ==="; echo "png: $(ls "$LORE"/*.png 2>/dev/null|wc -l)  txt: $(ls "$LORE"/*.txt 2>/dev/null|wc -l)"
echo DONE