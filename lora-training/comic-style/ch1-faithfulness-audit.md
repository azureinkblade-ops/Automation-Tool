# HA Chapter 1 - FAITHFULNESS AUDIT + INGEST NOTE (2026-07-16)
Source of truth: `youtube-videos/ha-1-chapter-1/chapter-text.txt` (213 lines)
Reviewer pass: vision_analyze on each GPT-generated page, checked verbatim against chapter text.

## OUTCOME
16 candidate images reviewed. 14 INGESTED as faithful, 2 REJECTED.
Ingested into `lora-training/comic-style/approved/` as **azink_comic_020 - 033** (+ paired captions).

## INGESTED (faithful, verbatim text correct) -> azink_comic_020-033
| ID | Beat | Key verbatim confirmed |
|----|------|------------------------|
| 020 | Opening stats screen | [Heavenly Ascension System] / Dormant Ember / Qi Circulation Minimal / Current Realm Mortal / STR2 END2 AGI2 VIT2 SPR3 PER2 FOC2 |
| 021 | Denial (mirror/bed) | "HE TRIED THE OBVIOUS THINGS FIRST" / "THE PANEL REMAINED" / "BY FOUR... CURIOSITY" |
| 022 | Morning from the floor | "KAI WATCHED MORNING ARRIVE FROM THE FLOOR" / "LIVING ON CREDIT" / "NOT GOOD. NOT HEALTHY. DIFFERENT." |
| 023 | Rent / 6:15 alarm | "OF COURSE" / "RENT WAS STILL DUE" / "IT DID NOT COME" |
| 024 | Daily Mortal Task | Stabilize the Body / Walk 1km / breathing 20 / squats 10 / Minor Vitality Integration / Failure Penalty: None / "NO PENALTY" |
| 025 | Stairwell -> lobby | "NOT NOW" / "TODAY HE REACHED THE LOBBY..." / "YOU COUNTED THE STAIRS?" / Walk 0.2/1 |
| 026 | City street / Qi sense | "THE CITY MOVED AROUND KAI WITHOUT SEEING HIM" / "AIR FELT LAYERED" / [Perception +0.1] / "POINT ONE?" |
| 027 | Convenience store / Marta | "YOU'RE EARLY" ... "THAT MEANS NO" (full exchange) |
| 028 | Morning rush / training | breathing 3/20, 5/20 / "REBUILT ONE CAREFUL PIECE AT A TIME" |
| 029 | Alley meeting (coat man) | "NEWLY AWAKENED" / "LEAKING QI ... THREE BLOCKS ... FOLLOW YOU HOME" |
| 030 | Pressure / endure | [Emergency Task Triggered] / Endure 30s / Forced collapse / 30-29-25 / "NORMAL LIFE ... A FEW WALLS AWAY" / IN OUT / 6/20 -- INVISIBLE pressure, braced on wall (canon-correct) |
| 031 | "Who taught you" | "WHO TAUGHT YOU?" / "NO ONE" / Complete / Vitality +0.2 / Focus +0.1 |
| 032 | Card / "what are you" | "AZURE MERIDIAN HALL NORTH HOLLOW" / "SOMEONE WHO NOTICED FIRST" |
| 033 | New objective / standing | Investigate Azure Meridian Hall / "YOU FALL INTO THE DUMPSTER OR WHAT?" / "STANDING WOULD HAVE TO BE ENOUGH" |

## REJECTED (do NOT ingest, do NOT train)
### R1 - "THUD" knockdown page  [RESOLVED 2026-07-17 -> replaced by azink_comic_034]
- WHY: Non-canon VISUAL. Shows Kai physically slammed to the ground, box spilling, debris
  flying, big "THUD" impact after "you also have thirty seconds."
- CANON: There is NO knockdown. The coat man exerts INVISIBLE spiritual pressure
  ("Pressure dropped over him like invisible weight... his knees bent"). Kai sinks under
  pressure and ENDURES the 30s Emergency Task braced against the wall - never struck,
  never sprawled, no flying debris, no THUD.
- Dialogue on the page ("THAT IS OBVIOUS / I DON'T KNOW WHAT THAT MEANS / YOU ALSO HAVE
  THIRTY SECONDS / I HAVE WORK") is verbatim-correct; only the art is wrong.
- RESOLUTION (2026-07-17): a corrected regen was produced (invisible-pressure buckling,
  box tips, kneels/braces on wall, coat man still with hands in pockets, no THUD/impact/
  purple haze, all text verbatim). TWO clean renders were reviewed; the stronger one
  (composer_2026-07-17_16-08-27 da2a78: ink 9.5, Kai-consistency 10) was INGESTED as
  **azink_comic_034_ch1_pressure_trigger**. The other render (13:48 787b98) was NOT
  ingested (near-duplicate, no training value). The THUD page itself remains rejected.

### R2 - garbled 40-panel auto-assembled strip
- WHY: Hallucinated / corrupted text. Confirmed errors:
  - Stat panel reads "Corrupted Ender" / "Current Eater" and "Blood Circulation"
    (canon = Dormant Ember / Qi Circulation / Current Realm); stats scrambled (AGI3 FOC3).
  - Invents an entire "Council" plotline ("Council would have you killed", "Council never
    went anywhere without seeing him") - NOT in Chapter 1.
  - "Item Injection / Overclock / System Status: Critical" - fabricated; canon reward is
    Qi Circulation Stabilization / Vitality +0.2 / Focus +0.1.
  - Mangled captions ("THAT MAKES 10", "HE WATCHED ALWAYS ARRIVE FROM THE CLOUDS").
- STATUS: Early auto-assembly draft, SUPERSEDED by the 14 clean individual pages. Discard.

## STANDING PLAN (user directive 2026-07-16)
- Build a FAITHFUL adaptation for EACH novel before training the comic LoRA:
  EN (Kael / Eternal Nexus), HA (Kai - done: prologue + ch1), HP (Liang / Hundredfold Path),
  SF (Jarek / Soulforge Era). Same pipeline: GPT-gen -> audit vs chapter-text.txt -> ingest faithful.
- Once all four novels have faithful sets in approved/, USER runs azink_comic LoRA training
  (may take a few days). Next free ID = azink_comic_034.
- Pre-flight before training: normalize approved/ to 1024^2 (train-1024/). App server must be
  DOWN during training (VRAM contention). azink_comic stays ON HOLD until user greenlights.

## DATASET STATE @ this note
approved/ = 24 faithful pages: prologue 011-019 (9) + ch1 020-033 (14) + ch1 pressure-trigger 034 (1). All paired captions.
rejected/text-heavy-panels-quarantine-2026-07-16/ = old 10 text-heavy panels (001-010).
HA novel = COMPLETE (prologue + full chapter 1). Next free ID = azink_comic_035 (for EN / HP / SF).
