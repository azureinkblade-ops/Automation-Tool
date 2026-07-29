# Stage 2 V1 — High-Resolution Subtle-Defect Review Rubric (ordinal)

Second-pass visual review of the quarantined V1 candidates. This complements
(not replaces) the coarse 7-gate structured review. Purpose: catch subtle
defects a 384px contact-sheet thumbnail and a binary accept/reject gate miss.

## Scoring scale (ordinal, per item)

| Score | Meaning |
|------:|---------|
| 3 | No visible issue. Refinement is clean at 100–200% zoom. |
| 2 | Minor issue. Perceptible only on close inspection; not distracting. |
| 1 | Moderate defect. Noticeable; would concern a careful viewer. |
| 0 | Severe defect. Clearly broken / wrong; unacceptable. |

Scores are per-item, not an average. A single 0 on a safety-relevant item
(grip, finger intersection, edge blending, halo) is a blocking defect for
that candidate even if other items are 3.

## Items (10)

1. **Grip alignment** — wrist/hand orientation matches the weapon grip; the hand
   closes on the hilt naturally, not floating beside it.
2. **Blade perspective** — blade foreshortening and perspective are consistent
   with the pose and camera; no flattened or wrongly-angled blade.
3. **Finger intersections** — fingers do not pass through the blade, guard, or
   grip; no missing/merged fingers over the weapon.
4. **Lighting consistency** — illumination, shadow direction, and intensity on
   the inserted object match the surrounding scene.
5. **Metal reflections** — metal reads as metal (specular, environment-aware),
   not matte plastic or uniformly gray.
6. **Edge blending** — object boundary blends into the underlying image; no hard
   cut-out seam.
7. **Texture continuity** — surface texture (and any attached straps/strings)
   continues plausibly with the character and surroundings.
8. **Halo artifacts** — no bright outline / contrast halo around the inserted
   object against the background.
9. **Scabbard attachment** — when a scabbard/sheath is present, it attaches to
   the body/belt/clearly-supported point correctly (not floating).
10. **Overall realism** — holistic believability of the edit in context.

## Reviewer identity

Each review records `reviewer`. Two allowed values:
- `human` — authoritative; the engineering reviewer inspected at full resolution.
- `auxiliary-vision-proxy` — machine first-pass via the vision model. LOW
  reliability for items 1–3, 6, 8 (sub-pixel / subtle). Treat as a triage
  signal only; human confirmation required before any score is treated as
  evidence.

## Relationship to the V1 report

The coarse 7-gate review (overall_accept) is the descriptive gate. This ordinal
rubric is the fine-grained layer. Both feed the frozen V1 report; neither
implies activation. V1-derived thresholds (if any are adopted) are frozen from
this review + the 7-gate results, BEFORE V1H begins.
