#!/usr/bin/env bash
# Ingest SF (Soulforge Era, Jarek) prologue + Chapter 1 into sf_comic/.
# Prologue = 001-002 (verbatim-audited against supplied prologue text).
# Chapter 1 = 003-008 (verbatim-audited against sf-1-chapter-1-embers-in-the-ash).
set -euo pipefail
SRC="$HOME/AppData/Roaming/Hermes/composer-images"
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
SF="$BASE/sf_comic"; mkdir -p "$SF"
add () { cp "$SRC/$1" "$SF/$2.png"; printf '%s\n' "$3" > "$SF/$2.txt"; echo "  + $2"; }

# --- PROLOGUE (001-002) ---
add composer_2026-07-18_16-25-58-393_762f44.png sf_comic_001_sf_prologue_street \
"sf_comic, vertical gritty dieselpunk manhwa page, desaturated browns greys deep shadows with warm artificial light, young scavenger Jarek with dark messy hair in a heavy armored jacket over a red shirt, crowded industrial slum street at night with steam and haze, Korean signage 검은화염교 Black Flame Cult and Furnace District 3, intimate shot counting coins at a metal counter with a meat pie behind glass, claustrophobic corridors of rusty pipes, dark woodcut ink style"

add composer_2026-07-18_16-25-58-405_6582b2.png sf_comic_002_sf_prologue_rings \
"sf_comic, vertical gritty dark-fantasy manhwa page, deep blues blacks greys warm oranges, a colossal circular orbital ring-city glowing against a starry sky above a tiered industrial metropolis, undercity slum gathered around a furnace for warmth, a massive swirling vortex of black fire and shadow erupting with hooded cultists in red-circle robes raising hands, a hovering drone spotlight and a yellow biohazard 경고 warning sign, cinematic prologue spread"

# --- CHAPTER 1 (003-008) ---
add composer_2026-07-18_16-25-58-384_93a265.png sf_comic_003_sf_ch1_opening \
"sf_comic, vertical gritty manhwa page, desaturated browns greys blacks with warm orange light, collapsed ruined subway tunnel with twisted train tracks leading into darkness, young Jarek with spiky dark hair in a padded jacket and backpack walking away from viewer, distant city skyline with lit windows through a gap in the ruins, a large muscular gang member with a shark-teeth vest brandishing a pipe saying MOVE IT RAT, wet reflective ground, chapter title EMBERS IN THE ASH"

add composer_2026-07-18_16-25-58-397_5b3a40.png sf_comic_004_sf_ch1_door \
"sf_comic, vertical gritty monochrome manhwa page, heavy black ink cross-hatching with red orange highlights, dark industrial tunnel with train tracks, ragged survivors and an Iron Seven licensed man with a 7 patch, a large jagged portal tearing open in the concrete wall glowing molten red and orange, Jarek bent over clutching his midsection as heat arrives, a shadow-wolf beast with glowing red eyes stepping through wrapped in rusted chains, Korean Black Flame Cult signage"

add composer_2026-07-18_16-25-58-397_46b8f3.png sf_comic_005_sf_ch1_chains \
"sf_comic, vertical gritty monochrome manhwa page, black ink with orange gold accents, industrial brick tunnel with railway tracks and a wall lantern, Jarek seen from behind hurling a pipe at a massive chain-wrapped shadow-wolf with glowing orange eyes, a burst of golden sparkling spiritual energy erupting from his hand striking the beast, a terrified child clutching an object by the lantern, the wolf recoiling as golden rune-inscribed chains fly from Jarek's raised empty hands and wrap the creature"

add composer_2026-07-18_16-25-58-405_5e9f80.png sf_comic_006_sf_ch1_forge_rats \
"sf_comic, vertical gritty high-contrast manhwa page, blacks dark greys browns with red text, a chaotic exodus of goggled Forge Rats sprinting through a wet industrial tunnel past a shadowy chained wolf-monster, Jarek with a cap and backpack looking back over his shoulder while a long-haired girl crawls reaching for a stone block, a green traffic signal, the shadow-wolf chained to the wall looming with red eyes, dramatic reflective lighting"

add composer_2026-07-18_16-25-58-414_d9da39.png sf_comic_007_sf_ch1_forge \
"sf_comic, vertical gritty monochrome manhwa page, deep blacks dark greys with warm golden-orange magic, industrial corridor with pipes and a doorway, Jarek straining backward wrapped in glowing golden rune chains pulling against a lunging shadow-wolf, close-up of him gripping the chain with both hands bared in pain wearing glowing runic bracers, a bright geometric diamond core bursting from his chest as the wolf dissolves into ash and light, etched woodcut texture"

add composer_2026-07-18_16-25-58-414_31aa4f.png sf_comic_008_sf_ch1_silence \
"sf_comic, vertical gritty ink manhwa page, deep blacks dark browns muted golds, Jarek crouching in a dim tunnel with glowing golden arm-markings staring at his hands, then kneeling beside a worried long-haired girl holding a heavy stone block as helmeted goggled men with a glowing tablet watch from deeper in the tunnel, frantic running through a cavernous hall with spotlights cutting dust, END OF CHAPTER 1"

echo "=== sf_comic ==="; echo "png: $(ls "$SF"/*.png|wc -l)  txt: $(ls "$SF"/*.txt|wc -l)"
echo DONE