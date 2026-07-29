#!/usr/bin/env bash
# Ingest 8 faithful HP Chapter-1 manhwa pages into azink_comic training set (035-042).
# Style NOTE: HP renders as sepia/brown ink-wash wuxia (NOT the blue-noir HA style).
# Captions describe BOTH the scene and the sub-style so the LoRA learns the range.
set -euo pipefail
SRC="$HOME/AppData/Roaming/Hermes/composer-images"
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
APP="$BASE/approved"; CAP="$BASE/captions"
mkdir -p "$APP" "$CAP"

ingest () { cp "$SRC/$1" "$APP/$2.png"; printf '%s\n' "$3" > "$CAP/$2.txt"; echo "  + $2"; }

# 035 - awakening (img 1070f1)
ingest composer_2026-07-18_00-24-46-686_1070f1.png azink_comic_035_hp_awakening_valley \
"azink_comic, vertical manhwa page, sepia and charcoal ink-wash wuxia style, young injured man Liang with long dark ponytail lying on jagged stone in a misty valley, copper sky with serpentine clouds, blood and dirt on face, tattered dark robes, muted browns and blacks with faint warm glow, atmospheric webtoon panel"

# 036 - sparrow whisper (img 5a69a0)
ingest composer_2026-07-18_00-24-46-703_5a69a0.png azink_comic_036_hp_sparrow_whisper \
"azink_comic, vertical manhwa page, sepia ink-wash wuxia style, wounded Liang kneeling on rocky ground reaching toward a small dark bird perched on a stone, desolate misty mountains, later the bird ascends dissolving into sparks of light merging with swirling clouds, muted browns orange and grey, dramatic atmospheric webtoon"

# 037 - closing / sparrow follows + sect (img 57535a)
ingest composer_2026-07-18_00-24-46-713_57535a.png azink_comic_037_hp_toward_sect \
"azink_comic, vertical manhwa page, sepia ink-wash wuxia style, Liang with scar on cheek looking back over shoulder at a small bird perched on a ledge, vast misty mountain range with ancient pagoda-style temple built into the cliffside, warm dawn light, muted browns and soft golds, cinematic webtoon"

# 038 - beast emerges (img 07a564)
ingest composer_2026-07-18_00-24-46-724_07a564.png azink_comic_038_hp_beast_emerges \
"azink_comic, vertical manhwa page, sepia monochrome ink-wash style, Liang climbing a jagged rock face then facing a monstrous shadow-wolf with glowing red eyes and long metallic claws emerging from mist, turbulent reddish storm sky, heavy fog, gritty survival atmosphere"

# 039 - threads climb (img a7efc0)
ingest composer_2026-07-18_00-24-46-734_a7efc0.png azink_comic_039_hp_threads_climb \
"azink_comic, vertical manhwa page, high-contrast black-and-white ink-wash style, Liang climbing a sheer rock face with glowing white threads extending from his fingertips to stable and crumbling stones, a shadow beast with red eyes reaching from the cliff, deep misty chasm below, magical thread system webtoon"

# 040 - realization + sect reveal (img eb34ed)
ingest composer_2026-07-18_00-24-46-742_eb34ed.png azink_comic_040_hp_spiral_real \
"azink_comic, vertical manhwa page, sepia-toned ink-wash style, Liang lying then leaning forward revealing a glowing white spiral mark on his bare chest, behind him a sprawling ancient cliffside civilization of tiered pagodas and winding stone staircases with calligraphy banners, warm ethereal sunlight, soft golds"

# 041 - countless liangs (img e7de1d)
ingest composer_2026-07-18_00-24-46-742_e7de1d.png azink_comic_041_hp_countless_liangs \
"azink_comic, vertical manhwa page, monochrome ink-wash style with glowing white and gold, Liang clutching his torn robe revealing a golden-white spiraling energy sigil on his chest, the spiral expands into a web of lightning-like energy connecting five floating shards each holding a different version of the protagonist, cosmic chaotic sky, supernatural awakening webtoon"

# 042 - choose (img 775624)
ingest composer_2026-07-18_00-24-46-743_775624.png azink_comic_042_hp_choose \
"azink_comic, vertical manhwa page, dark ink-wash style, Liang encased in a web of glowing white threads between two shadowy demonic beasts with red eyes, then clinging to a craggy cliff as a massive smoke beast with claws lunges, jagged KRAK sound effect, stormy grey sky, tense survival webtoon"

echo "=== approved total ==="; ls "$APP"/*.png | wc -l
echo "DONE"