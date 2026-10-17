"""Canonical Studio Bible character/location scoping (CPU-only).

Calls the adapter selectors and derive_spec_inputs directly. Fixtures list the
wrong novel's character and location first so characters[0] / locations[0]
selection would fail.

Unknown scene behavior (select_location_record): when the request novel has a
matching location pool and the scene names/implies a setting that does not match
name, id, or deterministic aliases in that pool, the selector fails closed
(returns None). LOCATION_FALLBACK_REMOVED: it does not inject pool[0] for
unmatched implied settings (e.g. EN "Nexus city" resolves to en_nexus_city when present and must never become en_nexus_pod).
Empty / non-implying scenes still use the novel-pool default. If the request
novel matches no location pool, return None (no cross-novel fallback).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.studio_bible_adapter as adapter  # noqa: E402


EN_CHARACTER = """
name: Kael Veyra
novel: en
appearance:
  hair:
    style: dark short
  eyes:
    color: blue
  body_type: lean_gamer
  age: young_adult
clothing:
  - obsidian tech shell
weapons:
  - Soulblade
magic_style: glyphs
"""

HA_CHARACTER = """
name: Kai
novel: ha
appearance:
  hair:
    style: short
  eyes:
    color: brown
  body_type: sickly_thin
  age: 19
clothing:
  - gray shirt
weapons:
  - amber qi threads
magic_style: amber qi
"""

EN_LOCATION = """
- name: Kael's neon apartment
  id: en_apt
  novel: en
  architecture: obsidian pod shell
  lighting: neon spill
  weather: n/a
  banners: none
  damage_state: intact
"""

HA_LOCATION = """
- name: Kai's rainy alley
  id: ha_alley
  novel: ha
  architecture: urban concrete
  lighting: rain reflections
  weather: rain
  banners: none
  damage_state: grime
"""

STYLE = """
novel: mixed
palette:
  primary: "#112233"
"""

EN_SCENE = "Kael Veyra stands in Kael's neon apartment, Soulblade drawn."
HA_SCENE = "Kai waits in the rain."
UNNAMED_SCENE = "rain falls on an unnamed street, no subject is spoken."
UNKNOWN_CHARACTER_SCENE = "Zara Quill waits beside an unnamed crossing."


def _make_bible(char_yamls, loc_yaml):
    root = Path(tempfile.mkdtemp(prefix="canon_scope_"))
    chars = root / "characters"
    locs = root / "locations"
    styles = root / "style_guides"
    chars.mkdir()
    locs.mkdir()
    styles.mkdir()
    for i, text in enumerate(char_yamls):
        (chars / f"char{i}.yaml").write_text(text, encoding="utf-8")
    (locs / "locations.yaml").write_text(loc_yaml, encoding="utf-8")
    (styles / "en.yaml").write_text(STYLE, encoding="utf-8")
    (styles / "ha.yaml").write_text(STYLE, encoding="utf-8")
    return root


# Wrong character and location listed first for an HA request.
HA_WRONG_FIRST = _make_bible(
    [EN_CHARACTER, HA_CHARACTER],
    EN_LOCATION + "\n" + HA_LOCATION,
)
# Wrong character and location listed first for an EN request.
EN_WRONG_FIRST = _make_bible(
    [HA_CHARACTER, EN_CHARACTER],
    HA_LOCATION + "\n" + EN_LOCATION,
)

DERIVE_KEYS = {
    "character_id",
    "subjects",
    "environment",
    "props",
    "palette",
    "lighting_design",
    "object_class",
    "object_state",
    "object_identity",
    "lighting",
    "negative_constraints",
    "unresolved_fields",
    "canon_warnings",
    "hair",
    "eyes",
    "magic_style",
    "magic_effects",
    "identity_lock",
    "camera_phrase",
    "shot_language",
    "lighting_phrase",
    "camera_intent_id",
    "lighting_intent_id",
}


class BiblePatchMixin:
    def setUp(self):
        self._saved = (
            adapter.CHARACTERS_DIR,
            adapter.LOCATIONS_DIR,
            adapter.STYLE_DIR,
        )

    def tearDown(self):
        (
            adapter.CHARACTERS_DIR,
            adapter.LOCATIONS_DIR,
            adapter.STYLE_DIR,
        ) = self._saved

    def _use(self, bible):
        adapter.CHARACTERS_DIR = bible / "characters"
        adapter.LOCATIONS_DIR = bible / "locations"
        adapter.STYLE_DIR = bible / "style_guides"

    def _project(self, bible, novel, scene):
        self._use(bible)
        return adapter.build_projection(novel, "ch1", scene)


class CanonScopingTest(BiblePatchMixin, unittest.TestCase):
    def test_en_character_canon_does_not_leak_into_ha(self):
        proj = self._project(HA_WRONG_FIRST, "ha", HA_SCENE)
        self.assertEqual(proj.characters[0].name, "Kael Veyra")
        char = adapter.select_character_record(proj, HA_SCENE)
        self.assertIsNotNone(char)
        self.assertEqual(char.name, "Kai")
        self.assertEqual(char.character_id, "kai")
        self.assertEqual(char.novel, "ha")
        inputs = adapter.derive_spec_inputs(proj, HA_SCENE)
        self.assertEqual(set(inputs), DERIVE_KEYS)
        self.assertEqual(inputs["character_id"], "kai")
        self.assertEqual(inputs["subjects"], ("Kai",))
        self.assertNotIn("Kael", " ".join(inputs["subjects"]))
        self.assertNotIn("kael_veyra", inputs["character_id"])
        self.assertNotIn("Soulblade", inputs["props"])
        self.assertNotIn("Soulblade", inputs["object_identity"])
        self.assertIn("amber qi", inputs["props"])

    def test_ha_character_canon_does_not_leak_into_en(self):
        proj = self._project(EN_WRONG_FIRST, "en", EN_SCENE)
        self.assertEqual(proj.characters[0].name, "Kai")
        char = adapter.select_character_record(proj, EN_SCENE)
        self.assertIsNotNone(char)
        self.assertEqual(char.name, "Kael Veyra")
        self.assertEqual(char.character_id, "kael_veyra")
        self.assertEqual(char.novel, "en")
        inputs = adapter.derive_spec_inputs(proj, EN_SCENE)
        self.assertEqual(inputs["character_id"], "kael_veyra")
        self.assertEqual(inputs["subjects"], ("Kael Veyra",))
        self.assertNotIn("Kai", inputs["subjects"])
        self.assertNotIn("kai", inputs["character_id"])
        self.assertEqual(inputs["object_identity"], "Soulblade")
        self.assertIn("Soulblade", inputs["props"])
        self.assertNotIn("amber qi", inputs["props"])
        self.assertNotIn("amber qi", inputs["object_identity"])

    def test_en_location_canon_does_not_leak_into_ha(self):
        proj = self._project(HA_WRONG_FIRST, "ha", HA_SCENE)
        self.assertEqual(proj.locations[0].location_id, "en_apt")
        loc = adapter.select_location_record(proj, HA_SCENE)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.location_id, "ha_alley")
        self.assertEqual(loc.novel, "ha")
        inputs = adapter.derive_spec_inputs(proj, HA_SCENE)
        self.assertEqual(inputs["environment"], "Kai's rainy alley")
        self.assertNotIn("neon apartment", inputs["environment"])
        self.assertNotEqual(inputs["lighting"], "neon spill")

    def test_ha_location_canon_does_not_leak_into_en(self):
        proj = self._project(EN_WRONG_FIRST, "en", EN_SCENE)
        self.assertEqual(proj.locations[0].location_id, "ha_alley")
        loc = adapter.select_location_record(proj, EN_SCENE)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.location_id, "en_apt")
        self.assertEqual(loc.novel, "en")
        inputs = adapter.derive_spec_inputs(proj, EN_SCENE)
        self.assertEqual(inputs["environment"], "Kael's neon apartment")
        self.assertNotIn("rainy alley", inputs["environment"])
        self.assertNotEqual(inputs["lighting"], "rain reflections")

    def test_unnamed_scene_falls_back_to_novel_protagonist_not_characters_zero(self):
        proj = self._project(HA_WRONG_FIRST, "ha", UNNAMED_SCENE)
        self.assertEqual(proj.characters[0].character_id, "kael_veyra")
        char = adapter.select_character_record(proj, UNNAMED_SCENE)
        self.assertIsNotNone(char)
        self.assertEqual(char.character_id, "kai")
        self.assertEqual(char.novel, "ha")
        inputs = adapter.derive_spec_inputs(proj, UNNAMED_SCENE)
        self.assertEqual(inputs["character_id"], "kai")
        self.assertEqual(inputs["subjects"], ("Kai",))
        self.assertNotIn("Soulblade", inputs["props"])
        self.assertNotEqual(inputs["environment"], "Kael's neon apartment")

    def test_unknown_named_character_does_not_resolve_to_other_novel(self):
        # Request novel has no unique protagonist, so the other novel's
        # characters[0] must not be assigned. Identity stays empty.
        proj = self._project(HA_WRONG_FIRST, "sf", UNKNOWN_CHARACTER_SCENE)
        first = adapter.select_character_record(proj, UNKNOWN_CHARACTER_SCENE)
        second = adapter.select_character_record(proj, UNKNOWN_CHARACTER_SCENE)
        self.assertIsNone(first)
        self.assertIsNone(second)
        inputs = adapter.derive_spec_inputs(proj, UNKNOWN_CHARACTER_SCENE)
        self.assertEqual(inputs["character_id"], "")
        self.assertEqual(inputs["subjects"], ())
        self.assertEqual(inputs["props"], ())
        self.assertEqual(inputs["object_identity"], "")
        self.assertNotIn("kael_veyra", inputs["character_id"])
        self.assertNotIn("kai", inputs["character_id"])
        blob = " ".join(inputs["subjects"]) + " " + inputs["object_identity"]
        self.assertNotIn("Kael", blob)
        self.assertNotIn("Kai", blob)
        self.assertNotIn("Soulblade", inputs["props"])
        self.assertNotIn("amber qi", inputs["props"])

    def test_unknown_scene_does_not_pull_other_novel_location(self):
        # Unmatched implied setting fails closed (None); never other-novel loc,
        # and never request-novel pool[0] injection for unmatched cues.
        scene = "an unmapped courtyard, location not named"
        proj = self._project(HA_WRONG_FIRST, "ha", scene)
        self.assertEqual(proj.locations[0].location_id, "en_apt")
        loc = adapter.select_location_record(proj, scene)
        again = adapter.select_location_record(proj, scene)
        self.assertIsNone(loc)
        self.assertIsNone(again)
        inputs = adapter.derive_spec_inputs(proj, scene)
        self.assertEqual(inputs["environment"], "")
        self.assertNotIn("neon apartment", inputs["environment"])
        # Foreign apartment cue on HA with no HA match -> fail closed, not EN.
        other_named = "standing inside Kael's neon apartment"
        loc_other = adapter.select_location_record(proj, other_named)
        self.assertIsNone(loc_other)

    def test_explicit_novel_scoping_wins_over_list_order(self):
        for bible, novel, scene, char_id, loc_id in (
            (HA_WRONG_FIRST, "ha", HA_SCENE, "kai", "ha_alley"),
            (EN_WRONG_FIRST, "en", EN_SCENE, "kael_veyra", "en_apt"),
            (HA_WRONG_FIRST, "en", EN_SCENE, "kael_veyra", "en_apt"),
            (EN_WRONG_FIRST, "ha", HA_SCENE, "kai", "ha_alley"),
        ):
            proj = self._project(bible, novel, scene)
            char = adapter.select_character_record(proj, scene)
            loc = adapter.select_location_record(proj, scene)
            self.assertEqual(char.character_id, char_id)
            self.assertEqual(loc.location_id, loc_id)
            inputs = adapter.derive_spec_inputs(proj, scene)
            self.assertEqual(inputs["character_id"], char_id)
            self.assertEqual(
                inputs["environment"],
                "Kai's rainy alley" if novel == "ha" else "Kael's neon apartment",
            )

    def test_empty_object_character_id_does_not_fall_back_when_primary_selected(self):
        primary = adapter.CharacterVisualRecord(
            character_id="kai", name="Kai", novel="ha",
        )
        other = adapter.CharacterVisualRecord(
            character_id="kael_veyra", name="Kael Veyra", novel="en",
        )
        orphan = adapter.ObjectVisualRecord(
            object_id="soulblade",
            canonical_phrase="Soulblade",
            character_id="",
        )
        proj = adapter.StudioBibleProjection(
            novel="ha",
            scene_text="Kai waits.",
            characters=(other, primary),
            locations=(
                adapter.LocationVisualRecord(
                    location_id="en_apt", name="Kael's neon apartment", novel="en",
                ),
                adapter.LocationVisualRecord(
                    location_id="ha_alley", name="Kai's rainy alley", novel="ha",
                ),
            ),
            objects=(orphan,),
        )
        inputs = adapter.derive_spec_inputs(proj, "Kai waits.")
        self.assertEqual(inputs["character_id"], "kai")
        self.assertEqual(inputs["props"], ())
        self.assertEqual(inputs["object_identity"], "")
        self.assertNotIn("Soulblade", inputs["props"])

    def test_soulblade_guard_does_not_follow_unselected_character(self):
        other = adapter.CharacterVisualRecord(
            character_id="kael_veyra",
            name="Kael Veyra",
            novel="en",
            warnings=("soulblade listed in warnings",),
        )
        primary = adapter.CharacterVisualRecord(
            character_id="kai", name="Kai", novel="ha",
        )
        proj = adapter.StudioBibleProjection(
            novel="ha",
            characters=(other, primary),
            locations=(
                adapter.LocationVisualRecord(
                    location_id="ha_alley", name="Kai's rainy alley", novel="ha",
                ),
            ),
        )
        inputs = adapter.derive_spec_inputs(proj, "Kai waits.")
        self.assertNotIn("weapon became staff", inputs["negative_constraints"])
        self.assertNotIn("oversized weapon", inputs["negative_constraints"])

    def test_project_to_generation_spec_uses_same_selectors(self):
        proj = self._project(HA_WRONG_FIRST, "ha", HA_SCENE)
        spec = adapter.project_to_generation_spec(proj, pipeline="", seed=7, scene_text=HA_SCENE)
        self.assertEqual(spec.identity.character_id, "kai")
        self.assertEqual(spec.content.subjects, ("Kai",))
        self.assertEqual(spec.content.environment, "Kai's rainy alley")
        self.assertNotIn("Soulblade", spec.content.props)
        self.assertNotIn("Soulblade", spec.conditioning.object_identity)


if __name__ == "__main__":
    unittest.main(verbosity=2)
