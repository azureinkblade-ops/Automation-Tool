# -*- coding: utf-8 -*-
"""CPU tests for studio-bible scene-construction patch 20260916 (3 findings)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.studio_bible_adapter as adapter  # noqa: E402
from tools.realistic_pipeline_v2 import (  # noqa: E402
    RealisticPipelineV2,
    _derive_object_state_from_text,
    _realistic_positive_prompt,
)


class TestLocationFallbackRemoved(unittest.TestCase):
    def test_nexus_city_never_selects_en_nexus_pod(self):
        scene = "Kael stands in the Nexus city with the Soulblade at his side"
        proj = adapter.build_projection("en", "", scene)
        loc = adapter.select_location_record(proj, scene)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.location_id, "en_nexus_city")
        self.assertNotEqual(loc.location_id, "en_nexus_pod")
        inputs = adapter.derive_spec_inputs(proj, scene)
        self.assertEqual(inputs["environment"], "Nexus city neon skyline")
        self.assertNotIn("apartment", inputs["environment"].lower())
        self.assertNotIn("NexusPod", inputs["environment"])

    def test_explicit_nexuspod_apartment_still_selects_pod(self):
        scene = "Kael stands in the NexusPod apartment"
        proj = adapter.build_projection("en", "", scene)
        loc = adapter.select_location_record(proj, scene)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.location_id, "en_nexus_pod")

    def test_hfp_mountain_sect_to_hp_sect(self):
        scene = "Liang stands in the mountain sect courtyard"
        proj = adapter.build_projection("hp", "", scene)
        loc = adapter.select_location_record(proj, scene)
        self.assertEqual(loc.location_id, "hp_sect")

    def test_sfe_forge_undercity_to_sf_forge(self):
        scene = "Jarek stands in the forge undercity among hanging chains"
        proj = adapter.build_projection("sf", "", scene)
        loc = adapter.select_location_record(proj, scene)
        self.assertEqual(loc.location_id, "sf_forge")

    def test_unmatched_synthetic_fails_closed(self):
        scene = "Kael waits in an unmapped synthetic plaza district"
        proj = adapter.build_projection("en", "", scene)
        loc = adapter.select_location_record(proj, scene)
        self.assertIsNone(loc)


class TestEmptyObjectStateNotDrawn(unittest.TestCase):
    def test_state_derivation_matrix(self):
        cases = [
            ("at_side", "Soulblade at his side", ""),
            ("sheathed", "Soulblade sheathed at hip", "sheathed"),
            ("carried", "sword carried on back", "carried"),
            ("none", "Kai waits quietly", ""),
            ("holding", "holding Soulblade aloft", "drawn"),
            ("drawn", "Soulblade drawn", "drawn"),
        ]
        for label, text, expect in cases:
            got = _derive_object_state_from_text(text, "Soulblade")
            self.assertEqual(got, expect, label)

    def test_kael_at_side_not_holding(self):
        scene = (
            "Kael stands in the Nexus city with the Soulblade at his side "
            "as glyph interfaces activate around him."
        )
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="", scene_text=scene, prompt=scene
        )
        self.assertEqual(spec.conditioning.object_state, "")
        pos = _realistic_positive_prompt(spec)
        self.assertNotIn("holding Soulblade", pos)
        self.assertIn("Soulblade at side", pos)

    def test_liang_no_unauthorized_weapon_in_hand(self):
        scene = (
            "Liang stands in the mountain sect courtyard as mist moves "
            "around the jade hall and red banners."
        )
        spec = RealisticPipelineV2().build_spec(
            novel="hp", chapter="", scene_text=scene, prompt=scene
        )
        self.assertEqual(spec.conditioning.object_state, "")
        pos = _realistic_positive_prompt(spec).lower()
        self.assertNotIn("holding", pos)

    def test_jarek_chains_not_holding_unless_explicit(self):
        scene = "Jarek stands in the forge undercity among hanging chains and furnace glow."
        spec = RealisticPipelineV2().build_spec(
            novel="sf", chapter="", scene_text=scene, prompt=scene
        )
        self.assertEqual(spec.conditioning.object_state, "")
        pos = _realistic_positive_prompt(spec).lower()
        self.assertNotIn("holding", pos)

    def test_explicit_drawn_still_holds(self):
        scene = "Kael Veyra stands in his neon apartment, Soulblade drawn, glyphs pulsing."
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="", scene_text=scene, prompt=scene
        )
        self.assertEqual(spec.conditioning.object_state, "drawn")
        pos = _realistic_positive_prompt(spec)
        self.assertIn("holding Soulblade", pos)


class TestKaiCharacterRefsUnbound(unittest.TestCase):
    def test_kai_character_refs_empty_style_refs_milestone(self):
        scene = (
            "Kai stands in a rain-slick alley near the convenience store "
            "while the System HUD floats beside him."
        )
        proj = adapter.build_projection("ha", "", scene)
        primary = adapter.select_character_record(proj, scene)
        crefs = adapter._character_reference_bindings(primary)
        srefs = adapter._milestone_style_bindings(primary)
        self.assertEqual(crefs, ())
        self.assertTrue(srefs)
        self.assertIn("milestone-kai", srefs[0].asset_path.replace("\\", "/"))
        # Diagnostic file must still exist on disk (not deleted).
        self.assertTrue(adapter._KAI_APPROVED_REFERENCE.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
