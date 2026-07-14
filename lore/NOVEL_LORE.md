# Azure Inkblade — Novel Lore Profile
*Maintained by Hermes. Source: manuscript extraction (Eternal Nexus - Updated Pass 1.docx, Heavenly Ascension System (4).docx, Soulforge Era - Revised (1).docx, The Hundredfold Path - Updated Revision.docx) on 2026-07-13. Novels are STILL IN PROGRESS — treat all detail as current-draft, not final canon.*

## Status
All 4 novels are actively being written (not complete). My lane is support (promo copy, character art, LoRA/tooling) — NOT authorship. Don't assert endings, fill gaps, or write the story. Regenerate art if character looks evolve.

## Shared brand
- Persona: **Azure Inkblade** (author brand). Tools business: **Inkblade Author Studio** (Gumroad).
- 3 SDXL LoRA tracks: `azink_main` (heroic web-novel cover style), `azink_comic` (comic style), `azink_real` (realistic; WEIGHTS TRAINED 2026-07-13, 46.6MB @ loras/realistic_posts). main/comic NOT trained yet (need more source imgs).
- Protagonist distinction: **Kael (EN) ≠ Kai (HA)** — keep separate in datasets/art.

---

## EN — Eternal Nexus
- **Genre:** LitRPG / System Apocalypse, cyberpunk game-lit.
- **Protagonist:** **Kael Veyra** — starts in one-room apartment with a `NexusPod` (obsidian shell, blue glyphs).
- **Hook:** Game patch "Ascension Wars Update" wipes characters / launches new realm. Kael enters lethal game-world.
- **Power system:** VR/System-LitRPG. NexusPod, glyphs, Soulblade blueprints (e.g. *Eclipse Soulblade*), legacy classes, tempering, holo UI.
- **Scope:** ~122 chapters / 227k words. Ends Ch.120 "The Crown That Remembered Him" (identity/recognition payoff: Elyen, golden stair, archive).
- **Tone:** Neon-cyberpunk, blue/purple energy, obsidian tech.
- **Key names:** Kael Veyra, Elyen, Sera, Jorik, Helion, Aren, Arienne, Accord, Dominion, Soulblade, Nexus.
- **Art tags (azink_real):** cyberpunk-mystic, blue glyph glow, obsidian pod, Soulblade, neon apartment.
- **Promo angle:** "The patch erased his character. The war rewrote the world."

## HA — Heavenly Ascension System
- **Genre:** Urban Modern Cultivation / LitRPG.
- **Protagonist:** **Kai** — 19, sickly, poor convenience-store clerk (gray shirt w/ faded logo, black pants).
- **Hook:** Pale-blue [Heavenly Ascension System] panel appears; **Spiritual Core: Dormant Ember** awakens in chest. "Newly awakened" — mysterious man in alley senses leaking Qi.
- **Power system:** Modern cultivation. Qi, Dantian, Spiritual Core, mortal-integration sequences, perception/skill gains. Prologue: "Cultivation was not dead… the lie the world told itself." Buried war; heaven collects debts.
- **Scope:** ~84 chapters / 220k words. Ends Ch.80 "The Witness Beneath One" (cosmic mystery: Construct Seven, Root Index, "ONE"). Mid-arc mystery B-plot: **Mina** (witness statements, Dr. Park, Mrs. Yoon, Seo Jun, Stillforge) — thriller angle beyond pure cultivation.
- **Tone:** Rainy neon city, sickly-yet-awakening everyman, warm golden ember vs cool blue system UI.
- **Art tags (azink_real):** urban cultivation, golden ember chest-glow, amber qi threads, pale-blue HUD panel, rainy neon city.
- **Approved test render:** `loras/realistic_posts/test_kai_ha.png` (v2 — ember + qi confirmed; USER PICKED THIS AS BEST).
- **Promo angle:** "A dying clerk. A system in his chest. Heaven's debt comes due."

## SF — Soulforge Era
- **Genre:** Post-Apocalyptic Soul-Forging / Under-city.
- **Protagonist:** **Jarek** — scavenger in collapsed undercity (rust, oil, old rain). **Varik** = red-eyed companion/antagonist ("Warden"/"Predator").
- **Hook:** Jarek sees **gold in his own eyes** in reflection — soul-forging awakening. Undercity lies beneath burning "ring-city."
- **Power system:** Soulforge — souls, forging, the **Iron Choir** (chains, music-as-power), Wardens/Predators, debt-economy. Gritty, bodily, hunger-driven.
- **Scope:** ~117 chapters / 206k words. Ends Ch.116 "Ash Under the Snow" (restrained zen combat: "fourth strike never came… listening to the silence"). Mid: Ch.57 "A City That Refuses" (city "breathes in pain," Choir grooves pulse like heartbeat).
- **Tone:** Industrial-dystopian, embers/ash, gold-eyed awakening, chains + choir. Darker/grittier than EN/HA.
- **Art tags (azink_real):** ashpunk, gold-eyed scavenger, iron chains, forge-fire, ruined ring-city.
- **Approved test render:** `loras/realistic_posts/test_jarek_sf.png` (v2 — gold eyes, forge-fire, tunnel confirmed).
- **Promo angle:** "In the city beneath the city, souls are forged — and chained."

## HP — The Hundredfold Path
- **Genre:** Classical Xianxia / Sect Cultivation.
- **Protagonist:** **Liang** — awakens in valley in pain (molten-copper sky), climbs to a **sect**, carries a **Jade Token**.
- **Hook:** Rebirth/transmigration into cultivation world; joins sect; learns Qi from *On the Nature of Qi*; "ember at his core."
- **Power system:** Classical xianxia — Qi, Dantian/core, techniques, formations, tribulations, sects, banners, silver-edged weapons (fans, chains, horn-bow).
- **Scope:** ~140 chapters / 293k words (longest). Ends Ch.140 "The Forest of Unchosen Lives" (Liang "carried no weapon," surrounded by unchosen). Supporting: **Cai** (Instructor), **Zhao Ren**, **Elder Mo**.
- **Tone:** Traditional wuxia/xianxia, jade/sect aesthetics, mountains, frost, silver. Distinct from HA's *modern* cultivation.
- **Art tags:** belongs in `azink_main` (heroic cover style), NOT azink_real. Jade sect robes, mountain sect, silver weapons, qi core.
- **Approved test render:** `loras/realistic_posts/test_liang_hp.png` (v2 — jade robes, red banners confirmed; silver sword came out as staff, qi glow missing — noted).
- **Promo angle:** "Reborn with nothing but a jade token and an ember at his core."

---

## Cross-cutting notes
- **Three cultivation flavors:** HP = classical sect/xianxia; HA = modern urban; SF = soul-forge dystopia. Don't let one LoRA's style bleed across them.
- **No character LoRAs yet** — current `azink_real` is style-only, not character-consistent. Per-character datasets needed for recurring faces.
- **HA mystery B-plot** (Mina/Root Index) is a unique promo angle vs generic cultivation — underused so far.
- **SF "gold in the eyes"** awakening = strong cover hook, underused.
- **Art limitation noted:** SDXL drops held/coiled objects (Soulblade, silver sword, arm-chains) and subtle glows (qi) even at high guidance — accept as style proofs.

## File/asset map (2026-07-13)
- Trained LoRA: `loras/realistic_posts/pytorch_lora_weights.safetensors`
- Test renders: `test_kael.png` (cyberpunk Kael), `test_kai_ha.png` (HA Kai v2 ★), `test_kael_en.png` (EN Kael v2), `test_jarek_sf.png` (SF Jarek v2), `test_liang_hp.png` (HP Liang v2)
- Generator scripts: `tools/lora_training/gen_*.py`
- Backed up at: `backup/2026-07-13` (commit f37abac)

---

## Working relationship with David (learned from our conversations)
*David asked me to keep this lore file growing from our talks and to learn from how he asks and speaks. Started 2026-07-13; will keep adding.*

**Communication style**
- Short, declarative sentences. Go-ahead is often one word: "go", "push it", "create the lore file + skill".
- Delegates judgment: says "use your judgement" — wants me to decide, not ask.
- Collaborative "we" framing ("we can remove it once its gone", "we can't save anything else").
- Corrects mistakes directly and promptly (Kael-EN vs Kai-HA mix-up; the python-kill confusion). Values accuracy on character identity.
- Efficient pointers over pasted text: attaches docx files, drops GitHub URLs, lets me fetch.
- Art feedback by picking a favorite ("v2 is better", "image 2 is great") rather than detailed critique — then expects me to regenerate stronger if elements are missing.

**How he wants me to work**
- Project start: listen/absorb context before acting (his stated preference).
- Once directed: execute the FULL task end-to-end without re-confirming sub-steps.
- Match existing formats — never invent a new style (verbatim: "use the style that is already present").
- Verification matters: show real execution evidence, not claims. (Ad-hoc re-run > assertion.)
- GPU/process safety: he survived a crash from orphaned foreground processes; wants one tracked process at a time, no foreground pip, kill stray procs before training.
- Secret hygiene: rotate tokens (he reissues), never print/persist them; scrub by exact value not prefix.
- Pragmatic about temporary promos (LAUNCH banner: "we can remove it once its gone").
- Thinks about persistence/scalability: asked about expanding memory, mobile monitoring, remote status checks.

**What he's building toward**
- Maximize earnings from web novels via Azure Inkblade (persona) + Inkblade Author Studio (Gumroad tools).
- Tooling > manual: prefers automated pipelines (app.py, LoRA training, scheduled backups).
- Character/brand accuracy is high-value: Kael(EN) ≠ Kai(HA); don't let LoRA styles bleed across the 3 cultivation flavors.
- Novels are a live, evolving product — promo copy and art are current-angle, revisable as the story develops.
