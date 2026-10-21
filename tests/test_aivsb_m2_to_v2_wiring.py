"""AIVSB M2 -> V2 GenerationSpec wiring causal test (CPU-only, no GPU).

Wires the existing Studio Bible adapter (tools.studio_bible_adapter) into the
Realistic and Main Posts V2 GenerationSpec construction paths and proves the
narrow integration contract with deterministic CPU fixtures:

  1. adapter invoked by Realistic build path
  2. adapter invoked by Main Posts build path
  3. StudioBibleBinding populated
  4. snapshot hash/reference populated
  5. Studio Bible positive conditioning reaches workflow
  6. negative constraints reach workflow where fixture provides them
  7. caller_prompt preserved
  8. qualified profile conditioning preserved
  9. wrong-novel canon absent
 10. private canon path absent
 11. OFF/ON single-factor comparison
 12. same snapshot/request deterministic
 13. unresolved behavior matches existing adapter contract
 14. provenance matches projection/spec

Fixtures are hermetic per-novel bible dirs (EN = Zorbin, HA = Pemble) so the
cross-novel causal comparisons are clean and free of live-canon leakage.

No ComfyUI submit / GPU generation occurs. SHA verification reads the real
approved project assets (cached per process).
"""

import hashlib
import re
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.studio_bible_adapter as adapter  # noqa: E402
from tools.generation_spec import (  # noqa: E402
    StudioBibleBinding,
    generation_spec_sha256,
)
from tools.main_posts_pipeline_v2 import (  # noqa: E402
    MainPostsPipelineV2,
    run_main_posts_resolution,
)
from tools.realistic_pipeline_v2 import (  # noqa: E402
    RealisticPipelineV2,
    run_realistic_resolution,
)

# SYNTHETIC_TEST_FIXTURE: all character/location/style values below are made-up test tokens (no Studio Bible content).
EN_CHARACTER = """
name: Zorbin Quillfeather
novel: en
appearance:
  hair:
    style: dark short
  eyes:
    color: blue
  body_type: wiry_tester
  age: young_adult
clothing:
  - plaid fixture vest
  - orange zigzag trim
weapons:
  - Soulblade
magic_style: fixture sparks
lighting_preference: test lamp glow
"""

EN_LOCATION = """
- name: Zorbin's fixture loft
  id: en_apt
  novel: en
  architecture: fixture loft, cardboard test walls
  lighting: desk lamp spill, orange zigzag glow
  weather: n/a
  magic_effects: fixture sparks, test overlay
  banners: none
  damage_state: intact
"""

EN_STYLE = """
novel: en
title: Fixture Novel EN
palette:
  primary: "#1B2A6B"
  secondary: "#6C2BD9"
  accent: "#00E5FF"
"""

HA_CHARACTER = """
name: Pemble
novel: ha
appearance:
  hair:
    style: short
  eyes:
    color: brown
  body_type: lanky_fixture
  age: 19
clothing:
  - teal_fixture_shirt
  - khaki_fixture_pants
weapons:
  - foam saber blade
magic_style: copper test core
lighting_preference: overcast test drizzle
"""

HA_LOCATION = """
- name: Pemble's fixture yard
  id: ha_alley
  novel: ha
  architecture: fixture brick, test signage
  lighting: puddle reflections, copper rim glow
  weather: rain
  magic_effects: fixture aura, mint test HUD
  banners: none
  damage_state: grime
"""

HA_STYLE = """
novel: ha
title: Fixture Novel HA
palette:
  primary: "#FFD66B"
  secondary: "#4DA3FF"
  accent: "#FF2D78"
"""


def _make_bible(char_yaml: str, loc_yaml: str, style_yaml: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="aivsb_wire_"))
    chars = d / "characters"
    locs = d / "locations"
    styles = d / "style_guides"
    chars.mkdir(parents=True)
    locs.mkdir(parents=True)
    styles.mkdir(parents=True)
    (chars / "char.yaml").write_text(char_yaml, encoding="utf-8")
    (locs / "locations.yaml").write_text(loc_yaml, encoding="utf-8")
    (styles / "en.yaml").write_text(style_yaml, encoding="utf-8")
    (styles / "ha.yaml").write_text(style_yaml, encoding="utf-8")
    return d


EN_DIR = _make_bible(EN_CHARACTER, EN_LOCATION, EN_STYLE)
HA_DIR = _make_bible(HA_CHARACTER, HA_LOCATION, HA_STYLE)

EN_SCENE = "Zorbin Quillfeather stands in his fixture loft, Soulblade drawn, sparks pulsing."
HA_SCENE = "Pemble awakens in the fixture yard, amber foam saber at his side, copper glowing."

CALLER_PROMPT = "weekend promo moment, cinematic, high detail"
SEED = 1_000_003


def _patch_bible(dir_path: Path) -> None:
    adapter.CHARACTERS_DIR = dir_path / "characters"
    adapter.LOCATIONS_DIR = dir_path / "locations"
    adapter.STYLE_DIR = dir_path / "style_guides"


def _workflow_sha(wf: dict) -> str:
    return hashlib.sha256(
        json.dumps(wf, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _execution_id_for(profile: str, spec, wf: dict) -> str:
    digest = _workflow_sha(wf)[:16]
    return f"v2exec-{profile}-{generation_spec_sha256(spec)[:16]}-{digest}"


class BiblePatchMixin:
    def setUp(self):
        self._saved = (
            adapter.CHARACTERS_DIR,
            adapter.LOCATIONS_DIR,
            adapter.STYLE_DIR,
        )

    def tearDown(self):
        adapter.CHARACTERS_DIR, adapter.LOCATIONS_DIR, adapter.STYLE_DIR = self._saved


class TestAdapterInvokedRealistic(BiblePatchMixin, unittest.TestCase):
    def test_adapter_invoked_and_enrichment_recorded(self):
        _patch_bible(EN_DIR)
        calls = {"n": 0}

        real_build = adapter.build_projection

        def _counted(novel, chapter, scene_text):
            calls["n"] += 1
            return real_build(novel, chapter, scene_text)

        adapter.build_projection = _counted
        try:
            meta = {}
            spec = RealisticPipelineV2().build_spec(
                novel="en", chapter="ch1", scene_text=EN_SCENE,
                prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=meta,
            )
        finally:
            adapter.build_projection = real_build
        self.assertEqual(calls["n"], 1)
        self.assertTrue(meta.get("enrichment_applied"))
        self.assertIn("projection_sha256", meta)


class TestAdapterInvokedMainPosts(BiblePatchMixin, unittest.TestCase):
    def test_adapter_invoked_and_enrichment_recorded(self):
        _patch_bible(EN_DIR)
        calls = {"n": 0}
        real_build = adapter.build_projection

        def _counted(novel, chapter, scene_text):
            calls["n"] += 1
            return real_build(novel, chapter, scene_text)

        adapter.build_projection = _counted
        try:
            meta = {}
            spec = MainPostsPipelineV2().build_spec(
                novel="en", chapter="ch1", scene_text=EN_SCENE,
                prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=meta,
            )
        finally:
            adapter.build_projection = real_build
        self.assertEqual(calls["n"], 1)
        self.assertTrue(meta.get("enrichment_applied"))


class TestBindingPopulated(BiblePatchMixin, unittest.TestCase):
    def test_realistic_binding_populated(self):
        _patch_bible(EN_DIR)
        meta = {}
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=meta,
        )
        binding = spec.identity.studio_bible_binding
        self.assertIsInstance(binding, StudioBibleBinding)
        self.assertTrue(binding.snapshot_ref)
        self.assertTrue(binding.snapshot_sha256)
        self.assertEqual(binding.snapshot_sha256, meta["projection_sha256"])

    def test_main_posts_binding_populated(self):
        _patch_bible(EN_DIR)
        meta = {}
        spec = MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=meta,
        )
        binding = spec.identity.studio_bible_binding
        self.assertTrue(binding.snapshot_ref)
        self.assertTrue(binding.snapshot_sha256)
        self.assertEqual(binding.snapshot_sha256, meta["projection_sha256"])

    def test_snapshot_ref_not_private_path(self):
        _patch_bible(EN_DIR)
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED,
        )
        self.assertNotIn("C:\\", spec.identity.studio_bible_binding.snapshot_ref)
        self.assertNotIn(str(EN_DIR), spec.identity.studio_bible_binding.snapshot_ref)


class TestProjectionDistinct(BiblePatchMixin, unittest.TestCase):
    def _proj(self, dir_path, novel, scene):
        _patch_bible(dir_path)
        return adapter.build_projection(novel, "ch1", scene)

    def test_projections_differ_en_vs_ha(self):
        p_en = self._proj(EN_DIR, "en", EN_SCENE)
        p_ha = self._proj(HA_DIR, "ha", HA_SCENE)
        self.assertNotEqual(adapter.projection_sha256(p_en),
                            adapter.projection_sha256(p_ha))

    def test_specs_differ_en_vs_ha(self):
        _patch_bible(EN_DIR)
        spec_en = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)
        _patch_bible(HA_DIR)
        spec_ha = RealisticPipelineV2().build_spec(
            novel="ha", chapter="ch1", scene_text=HA_SCENE, seed=SEED)
        self.assertNotEqual(generation_spec_sha256(spec_en),
                            generation_spec_sha256(spec_ha))

    def test_workflow_conditioning_distinct_en_vs_ha(self):
        _patch_bible(EN_DIR)
        wf_en = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)).workflow
        _patch_bible(HA_DIR)
        wf_ha = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="ha", chapter="ch1", scene_text=HA_SCENE, seed=SEED)).workflow
        self.assertNotEqual(_workflow_sha(wf_en), _workflow_sha(wf_ha))
        # EN carries Zorbin/Soulblade/EN palette; HA carries Pemble/foam saber/HA palette (synthetic fixture canon).
        self.assertIn("Zorbin Quillfeather", wf_en["6"]["inputs"]["text"])
        self.assertIn("Soulblade", wf_en["6"]["inputs"]["text"])
        self.assertIn("Pemble", wf_ha["6"]["inputs"]["text"])
        self.assertIn("foam saber", wf_ha["6"]["inputs"]["text"])


class TestPositiveConditioningReachesWorkflow(BiblePatchMixin, unittest.TestCase):
    def test_realistic_positive_has_subjects_palette_environment(self):
        _patch_bible(EN_DIR)
        wf = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)).workflow
        pos = wf["6"]["inputs"]["text"]
        self.assertIn("Zorbin Quillfeather", pos)
        self.assertIn("Zorbin's fixture loft", pos)
        # Palette hex stays on structured spec metadata, not CLIP.
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)
        self.assertIn("#1B2A6B", spec.style.palette)
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?\b", pos))
        self.assertIn("Soulblade", pos)

    def test_main_posts_positive_has_subjects_palette(self):
        _patch_bible(EN_DIR)
        wf = run_main_posts_resolution(MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)).workflow
        pos = wf["6"]["inputs"]["text"]
        self.assertIn("Zorbin Quillfeather", pos)
        self.assertIn("#1B2A6B", pos)


class TestRealisticSubjectPresenceClause(BiblePatchMixin, unittest.TestCase):
    def test_realistic_positive_has_person_presence_and_name(self):
        _patch_bible(EN_DIR)
        wf = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)).workflow
        pos = wf["6"]["inputs"]["text"]
        self.assertIn("Zorbin Quillfeather", pos)
        self.assertTrue(pos.startswith("young adult wiry tester person, Zorbin Quillfeather"), pos)
        self.assertIn("plaid fixture vest", pos)
        self.assertIn("orange zigzag trim", pos)
        # Presence clause is prepended, so it precedes profile conditioning.
        self.assertLess(pos.find("young adult"), pos.find("photographic realistic"))
        # Name is still present after the clause (subjects unchanged in role).
        self.assertGreaterEqual(pos.count("Zorbin Quillfeather"), 1)


class TestRealisticWeaponNoteNotInPositive(BiblePatchMixin, unittest.TestCase):
    def test_en_like_positive_keeps_soulblade_strips_author_note(self):
        """Presence clause stays; parenthetical NOTE asides do not reach CLIP."""
        char = """
name: Zorbin Quillfeather
novel: en
appearance:
  hair:
    style: dark short
  eyes:
    color: blue
  body_type: wiry_tester
  age: young_adult
clothing:
  - fixture_outfit_alpha (start)
  - plaid_fixture_vest_orange_zigzag_trim (phase2)
  - Soulblade_at_side (NOTE: fixture renderer drops held props, accept)
weapons:
  - Soulblade
"""
        bible = _make_bible(char, EN_LOCATION, EN_STYLE)
        _patch_bible(bible)
        wf = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)).workflow
        pos = wf["6"]["inputs"]["text"]
        self.assertTrue(pos.startswith("young adult wiry tester person, Zorbin Quillfeather"), pos)
        self.assertIn("Soulblade", pos)
        # Drawn-state already rewrites the clothing phrase to "holding Soulblade".
        # Hex removal must not change that object token.
        self.assertIn("holding Soulblade", pos)
        self.assertNotIn("NOTE", pos)
        self.assertNotIn("drops held props", pos)
        # Author-note strip does not rewrite palette metadata; hex stays off CLIP.
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)
        self.assertIn("#1B2A6B", spec.style.palette)
        self.assertNotIn("#1B2A6B", pos)


class TestNegativeConstraintsReachWorkflow(BiblePatchMixin, unittest.TestCase):
    def test_realistic_canon_negatives_present_for_en(self):
        _patch_bible(EN_DIR)
        wf = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)).workflow
        neg = wf["7"]["inputs"]["text"]
        # CANON_NEGATIVE_CONSTRAINTS always present (identity-protecting canon
        # negatives propagated into the workflow negative conditioning).
        self.assertIn("incorrect weapon", neg)
        self.assertIn("missing character symbols", neg)

    def test_main_posts_canon_negatives_present_for_en(self):
        _patch_bible(EN_DIR)
        wf = run_main_posts_resolution(MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)).workflow
        neg = wf["7"]["inputs"]["text"]
        self.assertIn("incorrect weapon", neg)


class TestCallerPromptPreserved(BiblePatchMixin, unittest.TestCase):
    def test_realistic_caller_prompt_in_spec_and_workflow(self):
        _patch_bible(EN_DIR)
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)
        wf = run_realistic_resolution(spec).workflow
        self.assertEqual(spec.caller_prompt, CALLER_PROMPT)
        self.assertIn(CALLER_PROMPT, wf["6"]["inputs"]["text"])

    def test_main_posts_caller_prompt_preserved(self):
        _patch_bible(EN_DIR)
        spec = MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)
        wf = run_main_posts_resolution(spec).workflow
        self.assertIn(CALLER_PROMPT, wf["6"]["inputs"]["text"])


class TestProfileConditioningPreserved(BiblePatchMixin, unittest.TestCase):
    def test_realistic_profile_conditioning_present(self):
        _patch_bible(EN_DIR)
        wf = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)).workflow
        self.assertIn("photographic realistic automation-tool style",
                      wf["6"]["inputs"]["text"])

    def test_main_posts_profile_conditioning_present(self):
        _patch_bible(EN_DIR)
        wf = run_main_posts_resolution(MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)).workflow
        self.assertIn("Azure Inkblade chapter promo art",
                      wf["6"]["inputs"]["text"])


class TestWrongNovelCanonAbsent(BiblePatchMixin, unittest.TestCase):
    def test_en_workflow_free_of_ha_canon(self):
        _patch_bible(EN_DIR)
        wf = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)).workflow
        pos = wf["6"]["inputs"]["text"]
        self.assertNotIn("Pemble", pos)
        self.assertNotIn("#FFD66B", pos)
        self.assertNotIn("foam saber", pos)

    def test_ha_workflow_free_of_en_canon(self):
        _patch_bible(HA_DIR)
        wf = run_realistic_resolution(RealisticPipelineV2().build_spec(
            novel="ha", chapter="ch1", scene_text=HA_SCENE, seed=SEED)).workflow
        pos = wf["6"]["inputs"]["text"]
        self.assertNotIn("Zorbin", pos)
        self.assertNotIn("#1B2A6B", pos)
        self.assertNotIn("Soulblade", pos)


class TestNoPrivateCanonPathLeak(BiblePatchMixin, unittest.TestCase):
    def test_no_private_paths_in_prompts(self):
        _patch_bible(EN_DIR)
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)
        wf = run_realistic_resolution(spec).workflow
        blob = wf["6"]["inputs"]["text"] + " || " + wf["7"]["inputs"]["text"]
        self.assertNotIn("C:\\", blob)
        self.assertNotIn("Users", blob)
        self.assertNotIn(".yaml", blob)
        self.assertNotIn("Inkblade Author Studio", blob)
        self.assertNotIn("studio_bible_binding", blob)


class TestOffOnSingleFactor(BiblePatchMixin, unittest.TestCase):
    def test_off_on_realistic_only_studio_bible_differs(self):
        _patch_bible(EN_DIR)
        off_meta, on_meta = {}, {}
        off_spec = RealisticPipelineV2().build_spec(
            prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=off_meta)
        on_spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=on_meta)
        self.assertFalse(off_meta["enrichment_applied"])
        self.assertTrue(on_meta["enrichment_applied"])

        from tools.generation_spec import diff_generation_spec
        diff = diff_generation_spec(off_spec, on_spec)
        changed = set(diff["changed"])
        # Every changed GenerationSpec path must be a Studio Bible field.
        sb_paths = {
            "identity.character_id",
            "identity.studio_bible_binding.snapshot_ref",
            "identity.studio_bible_binding.snapshot_sha256",
            "content.subjects",
            "content.environment",
            "content.props",
            "style.palette",
            "style.lighting_design",
            "conditioning.object_class",
            "conditioning.object_state",
            "conditioning.object_identity",
            "conditioning.lighting",
            "conditioning.negative_constraints",
            "body_pose.person_geometry",
        }
        self.assertTrue(changed, "expected some SB field to change")
        self.assertEqual(changed, changed & sb_paths,
                         f"non-SB fields changed: {changed - sb_paths}")
        # Profile conditioning + caller prompt + asset execution unchanged.
        self.assertEqual(off_spec.style.style_profile, on_spec.style.style_profile)
        self.assertEqual(off_spec.caller_prompt, on_spec.caller_prompt)
        self.assertEqual(off_spec.model_execution, on_spec.model_execution)

        off_wf = run_realistic_resolution(off_spec).workflow
        on_wf = run_realistic_resolution(on_spec).workflow
        # Identical except positive (6), negative (7), and the spec-hash-derived
        # SaveImage prefix (8).
        differing_nodes = {
            nid for nid in off_wf
            if json.dumps(off_wf[nid], sort_keys=True) != json.dumps(on_wf[nid], sort_keys=True)
        }
        self.assertTrue(differing_nodes.issubset({"6", "7", "8"}),
                        f"unexpected node diff: {differing_nodes}")
        self.assertIn("Zorbin Quillfeather", on_wf["6"]["inputs"]["text"])
        self.assertNotIn("Zorbin Quillfeather", off_wf["6"]["inputs"]["text"])

    def test_off_on_main_posts_only_studio_bible_differs(self):
        _patch_bible(EN_DIR)
        off_spec = MainPostsPipelineV2().build_spec(prompt=CALLER_PROMPT, seed=SEED)
        on_spec = MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)
        from tools.generation_spec import diff_generation_spec
        diff = diff_generation_spec(off_spec, on_spec)
        changed = set(diff["changed"])
        sb_paths = {
            "identity.character_id",
            "identity.studio_bible_binding.snapshot_ref",
            "identity.studio_bible_binding.snapshot_sha256",
            "content.subjects",
            "content.environment",
            "content.props",
            "style.palette",
            "style.lighting_design",
            "conditioning.object_class",
            "conditioning.object_state",
            "conditioning.object_identity",
            "conditioning.lighting",
            "conditioning.negative_constraints",
        }
        self.assertEqual(changed, changed & sb_paths,
                         f"non-SB fields changed: {changed - sb_paths}")


class TestDeterminism(BiblePatchMixin, unittest.TestCase):
    def test_same_request_same_identities(self):
        _patch_bible(EN_DIR)
        spec1 = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)
        spec2 = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)
        self.assertEqual(generation_spec_sha256(spec1),
                         generation_spec_sha256(spec2))
        wf1 = run_realistic_resolution(spec1).workflow
        wf2 = run_realistic_resolution(spec2).workflow
        self.assertEqual(_workflow_sha(wf1), _workflow_sha(wf2))
        self.assertEqual(
            _execution_id_for("realistic", spec1, wf1),
            _execution_id_for("realistic", spec2, wf2),
        )

    def test_main_posts_deterministic(self):
        _patch_bible(EN_DIR)
        spec1 = MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)
        spec2 = MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE, seed=SEED)
        self.assertEqual(generation_spec_sha256(spec1),
                         generation_spec_sha256(spec2))


class TestUnresolvedMatchesAdapterContract(BiblePatchMixin, unittest.TestCase):
    def test_unresolved_fail_closed_when_no_bible(self):
        # Point at an empty dir: required canon unresolved -> fail closed.
        # No synthesis and no silent empty GenerationSpec for bible-driven V2.
        empty = Path(tempfile.mkdtemp(prefix="aivsb_empty_"))
        _patch_bible(empty)
        with self.assertRaises(adapter.CanonUnresolvedError) as ctx:
            RealisticPipelineV2().build_spec(
                novel="en", chapter="ch1", scene_text="a scene with no bible",
                seed=SEED, studio_bible_meta={})
        self.assertIn(ctx.exception.code, {
            adapter.CanonStatus.UNKNOWN_CHARACTER,
            adapter.CanonStatus.UNKNOWN_SCENE,
            adapter.CanonStatus.MISSING_REQUIRED_CANON,
        })


class TestProvenanceMatchesSpec(BiblePatchMixin, unittest.TestCase):
    def test_realistic_provenance_matches_spec(self):
        _patch_bible(EN_DIR)
        meta = {}
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=meta)
        prov = run_realistic_resolution(spec, studio_bible_meta=meta).provenance
        sb = prov["studio_bible"]
        self.assertEqual(sb["snapshot_ref"], spec.identity.studio_bible_binding.snapshot_ref)
        self.assertEqual(sb["snapshot_sha256"], spec.identity.studio_bible_binding.snapshot_sha256)
        self.assertEqual(sb["projection_sha256"], meta["projection_sha256"])
        self.assertTrue(sb["enrichment_applied"])
        self.assertNotIn("C:\\", sb["snapshot_ref"])

    def test_main_posts_provenance_matches_spec(self):
        _patch_bible(EN_DIR)
        meta = {}
        spec = MainPostsPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED, studio_bible_meta=meta)
        prov = run_main_posts_resolution(spec, studio_bible_meta=meta).provenance
        sb = prov["studio_bible"]
        self.assertEqual(sb["snapshot_sha256"], spec.identity.studio_bible_binding.snapshot_sha256)
        self.assertEqual(sb["projection_sha256"], meta["projection_sha256"])



class TestRealisticPaletteHexExcludedFromClip(BiblePatchMixin, unittest.TestCase):
    _HEX = re.compile(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?\b")

    def test_structured_palette_survives_clip_has_no_hex(self):
        _patch_bible(EN_DIR)
        spec = RealisticPipelineV2().build_spec(
            novel="en", chapter="ch1", scene_text=EN_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)
        resolved = run_realistic_resolution(spec)
        pos = resolved.workflow["6"]["inputs"]["text"]
        neg = resolved.workflow["7"]["inputs"]["text"]
        self.assertTrue(spec.style.palette)
        self.assertIn("#1B2A6B", spec.style.palette)
        self.assertRegex(spec.style.palette, r"#[0-9A-Fa-f]{6}")
        self.assertIsNone(self._HEX.search(pos))
        self.assertIsNone(self._HEX.search(neg))
        self.assertNotIn("primary #", pos)
        self.assertIn("Zorbin Quillfeather", pos)
        self.assertIn("Zorbin's fixture loft", pos)
        self.assertIn("Soulblade", pos)
        self.assertIn("photographic realistic automation-tool style", pos)

    def test_ha_structured_palette_survives_clip_has_no_hex(self):
        _patch_bible(HA_DIR)
        spec = RealisticPipelineV2().build_spec(
            novel="ha", chapter="ch1", scene_text=HA_SCENE,
            prompt=CALLER_PROMPT, seed=SEED)
        resolved = run_realistic_resolution(spec)
        pos = resolved.workflow["6"]["inputs"]["text"]
        neg = resolved.workflow["7"]["inputs"]["text"]
        self.assertIn("#FFD66B", spec.style.palette)
        self.assertIsNone(self._HEX.search(pos))
        self.assertIsNone(self._HEX.search(neg))
        self.assertIn("Pemble", pos)
        self.assertNotIn("primary #", pos)


if __name__ == "__main__":
    unittest.main(verbosity=2)


