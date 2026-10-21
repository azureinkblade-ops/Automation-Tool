# -*- coding: utf-8 -*-
"""CPU tests for Eternal Nexus city location mapping (studio-bible-en-city-location-20260916)."""
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
    _realistic_positive_prompt,
)


EN_CITY_ID = "en_nexus_city"
EN_POD_ID = "en_nexus_pod"
EN_CITY_NAME = "Nexus city neon skyline"


class TestEnNexusCityLocation(unittest.TestCase):
    def _loc(self, scene: str):
        proj = adapter.build_projection("en", "", scene)
        return adapter.select_location_record(proj, scene), proj

    def test_nexus_city_resolves_to_city_record(self):
        scene = "Kael stands in the Nexus city with the Soulblade at his side"
        loc, _ = self._loc(scene)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.location_id, EN_CITY_ID)
        self.assertEqual(loc.name, EN_CITY_NAME)
        self.assertNotEqual(loc.location_id, EN_POD_ID)

    def test_neon_city_skyline_consistent(self):
        for scene in (
            "Wide view of the neon city skyline with glyph interfaces",
            "Nexus skyline towers glow blue-purple",
            "Kael overlooks the Nexus urban neon towers",
            "neon city streets with holo interfaces",
            "standing in the city as glyphs activate",
        ):
            loc, _ = self._loc(scene)
            self.assertIsNotNone(loc, scene)
            self.assertEqual(loc.location_id, EN_CITY_ID, scene)
            self.assertNotEqual(loc.location_id, EN_POD_ID, scene)

    def test_nexuspod_still_pod(self):
        for scene in (
            "Kael stands in the NexusPod",
            "Kael waits in his apartment",
            "inside the Nexus pod with blue glyphs",
        ):
            loc, _ = self._loc(scene)
            self.assertIsNotNone(loc, scene)
            self.assertEqual(loc.location_id, EN_POD_ID, scene)

    def test_apartment_still_pod(self):
        scene = "Kael stands in the NexusPod apartment"
        loc, _ = self._loc(scene)
        self.assertEqual(loc.location_id, EN_POD_ID)

    def test_unmatched_en_still_fails_closed(self):
        scene = "Kael waits in an unmapped synthetic plaza district"
        loc, _ = self._loc(scene)
        self.assertIsNone(loc)

    def test_deterministic(self):
        scene = "Kael stands in the Nexus city with the Soulblade at his side"
        a, _ = self._loc(scene)
        b, _ = self._loc(scene)
        self.assertEqual(a.location_id, b.location_id)
        self.assertEqual(a.name, b.name)

    def test_no_cross_novel_aliases(self):
        # HA scene mentioning city neon must not resolve to EN city.
        scene = "Wide view of the rain-slick alley with distant city neon"
        proj = adapter.build_projection("ha", "", scene)
        loc = adapter.select_location_record(proj, scene)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.location_id, "ha_alley")
        self.assertNotEqual(loc.location_id, EN_CITY_ID)
        # SF forge undercity must not become EN city via "city" substring.
        scene_sf = "Jarek stands in the forge undercity among hanging chains"
        proj_sf = adapter.build_projection("sf", "", scene_sf)
        loc_sf = adapter.select_location_record(proj_sf, scene_sf)
        self.assertEqual(loc_sf.location_id, "sf_forge")
        self.assertNotEqual(loc_sf.location_id, EN_CITY_ID)

    def test_invariant_city_ne_pod(self):
        city, _ = self._loc("Nexus city neon skyline")
        pod, _ = self._loc("NexusPod apartment")
        self.assertEqual(city.location_id, EN_CITY_ID)
        self.assertEqual(pod.location_id, EN_POD_ID)
        self.assertNotEqual(city.location_id, pod.location_id)

    def test_kael_scene_environment_and_holding(self):
        scene = (
            "Kael stands in the Nexus city with the Soulblade at his side "
            "as glyph interfaces activate around him."
        )
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="", scene_text=scene, prompt=scene
        )
        proj = adapter.build_projection("en", "", scene)
        loc = adapter.select_location_record(proj, scene)
        inputs = adapter.derive_spec_inputs(proj, scene)
        self.assertEqual(loc.location_id, EN_CITY_ID)
        self.assertEqual(inputs["environment"], EN_CITY_NAME)
        self.assertEqual(spec.conditioning.object_state, "")
        pos = _realistic_positive_prompt(spec)
        self.assertIn("Soulblade at side", pos)
        self.assertNotIn("holding Soulblade", pos)
        self.assertIn(EN_CITY_NAME, pos)
        # Milestone style refs, empty character refs
        primary = adapter.select_character_record(proj, scene)
        crefs = adapter._character_reference_bindings(primary)
        srefs = adapter._milestone_style_bindings(primary)
        self.assertEqual(crefs, ())
        self.assertTrue(srefs)
        self.assertIn("milestone-kael", srefs[0].asset_path.replace("\\", "/").lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
