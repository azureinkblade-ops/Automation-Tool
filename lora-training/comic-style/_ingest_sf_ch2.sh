#!/usr/bin/env bash
# Ingest SF Chapter 2 (Jarek) faithful pages 009-014 into sf_comic/.
# Verbatim-audited against sf-2-chapter-2-the-price-of-being-seen/chapter-text.txt.
set -euo pipefail
SRC="$HOME/AppData/Roaming/Hermes/composer-images"
BASE="$HOME/Documents/Automation tool/lora-training/comic-style"
SF="$BASE/sf_comic"; mkdir -p "$SF"
add () { cp "$SRC/$1" "$SF/$2.png"; printf '%s\n' "$3" > "$SF/$2.txt"; echo "  + $2"; }

# 009 - cistern / glow / child
add composer_2026-07-18_19-01-18-043_da05ab.png sf_comic_009_sf_ch2_cistern \
"sf_comic, vertical gritty dieselpunk manhwa page, desaturated browns greys blacks warm amber glow, header CHAPTER 2 — THE PRICE OF BEING SEEN, Jarek kneeling exhausted at a cracked stone cistern in an underground industrial ruin, his reflection in the water with glowing slit-pupil gold eyes, a dirty young girl in a tattered hooded coat approaching, gold vein-light along Jarek's neck and arm, dark woodcut ink style"

# 010 - please / wards / fire answers
add composer_2026-07-18_19-01-18-048_b73400.png sf_comic_010_sf_ch2_wards \
"sf_comic, vertical gritty manhwa page, dark browns greys faint neon blue, Jarek pleading with the girl 'You didn't see me' as golden light fades along his arms, a massive armored Guild wagon with glowing blue ward-runes rumbling past on an old tram line, Jarek and the girl crouched behind a stone pillar, blue energy field washing over them, a red MORE hunger-UI button, cinematic undercity"

# 011 - Varik / keep moving / who are you
add composer_2026-07-18_19-01-18-051_7371de.png sf_comic_011_sf_ch2_varik \
"sf_comic, vertical gritty manhwa page, deep blacks greys faint neon blue, tall scarred mentor Varik Kest with a glowing red mechanical eye and patched coat leaning on an armored wagon saying KEEP MOVING, then facing Jarek and the clinging girl in a dark tunnel of pipes, 'You closed a door' 'Who are you' 'Varik Kest' 'I teach people to survive being noticed' 'I don't obey strangers' 'Then obey the facts', dieselpunk texture"

# 012 - gangs saw / hunger voice / third path
add composer_2026-07-18_19-01-18_055_a56f3a.png sf_comic_012_sf_ch2_hunger \
"sf_comic, vertical gritty high-contrast manhwa page, warm low light dark stone arches, Varik with a scarred red eye warning Jarek before masked gang members and hooded Black Flame cultists with a glowing sigil and a blue guild-record hologram, close-up of Jarek's face streaked with sweat as a glowing orange mark on his chest whispers MORE STRONGER TAKE AGAIN, 'That voice is not wisdom' 'A third path but it costs' 'What cost', woodcut ink"

# 013 - cost / chain anchor / invisible
add composer_2026-07-18_19-01-18_062_09b27b.png sf_comic_013_sf_ch2_terms \
"sf_comic, vertical gritty manhwa page, dark industrial wet stone, Varik laying down terms to Jarek while the girl clings to Jarek's arm — 'You listen when I say run' 'You choose what you are' — Jarek's counter 'She walks away clean, no Guild no gangs no cult', Varik's 'Good, a chain needs an anchor, keep that one', closing narration JAREK COULD NOT BECOME INVISIBLE AGAIN, orange-gold mark glow"

# 014 - warden / into the dark / end ch2
add composer_2026-07-18_19-01-18-064_2aa7c2.png sf_comic_014_sf_ch2_end \
"sf_comic, vertical gritty manhwa page, dark tunnel lined with pipes and machinery, Varik and Jarek walking away from viewer, 'Come on, Warden' 'Don't call me that' 'Predator, then' 'Let them argue over names, you worry about surviving the thing underneath them', a wall seam glowing faint red, closing narration WHISPERS WERE ALREADY LEARNING JAREK'S SHAPE and SOMETHING PRESSED AGAINST A SEAM AND CONSIDERED THE COST OF OPENING, JAREK FOLLOWED VARIK INTO THE DARK, END OF CHAPTER 2"

echo "=== sf_comic ==="; echo "png: $(ls "$SF"/*.png|wc -l)  txt: $(ls "$SF"/*.txt|wc -l)"
echo DONE