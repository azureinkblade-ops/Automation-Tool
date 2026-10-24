# -*- coding: utf-8 -*-
"""IDENTITY_PRODUCTION_PLUMBING_20260929 - flag-ON boundary tests + flag-OFF legacy.

CPU / spec only. GPU_GENERATIONS=0: no image generation, no ComfyUI submission.
Fixture "images" are small byte files in a temp dir; the verifier never reads pixels.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import generation_spec as gs  # noqa: E402
from tools import identity_preservation as ip  # noqa: E402
from tools import studio_bible_adapter as sba  # noqa: E402

FLAG = "ENABLE_IDENTITY_PRESERVATION"
# IdentitySpec keys that existed before IDENTITY_PRODUCTION_PLUMBING (from before_src generation_spec.py).
LEGACY_IDENTITY_KEYS = {"character_id", "character_version", "object_id", "object_version",
                        "studio_bible_binding", "reference_bindings"}

SCENES = {
    "kai": ("ha", "1", "Kai stood in the rain alley; he looked up at the System HUD."),
    "kael_veyra": ("en", "1", "Kael Veyra stepped into the neon city; he raised his Soulblade."),
    "liang": ("hp", "1", "Liang stood in the mountain sect courtyard in morning mist."),
    "liang_she": ("hp", "1", "Liang stood in the sect courtyard; she closed her eyes and sensed qi."),
    "liang_he": ("hp", "1", "Liang stood in the sect courtyard; he closed his eyes and sensed qi."),
    "jarek": ("sf", "1", "Jarek dragged iron chains through the forge undercity; his gold eyes burned."),
}


@contextlib.contextmanager
def flag(on: bool, **extra):
    saved = {k: os.environ.get(k) for k in (FLAG, "STYLE_REF_EXPERIMENTAL", "STYLE_REF_STRENGTH", "AIVSB_REASONING_ENABLED", *extra)}
    try:
        os.environ["AIVSB_REASONING_ENABLED"] = "off"  # AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: hermetic non-AIVSB rules
        os.environ.pop(FLAG, None)
        os.environ.pop("STYLE_REF_EXPERIMENTAL", None)
        os.environ.pop("STYLE_REF_STRENGTH", None)
        if on:
            os.environ[FLAG] = "1"
        for k, v in extra.items():
            os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def adapter_spec(key: str):
    nov, ch, scene = SCENES[key]
    proj = sba.build_projection(nov, ch, scene)
    return sba.project_to_generation_spec(proj, pipeline="realistic", seed=1, scene_text=scene)


def record_for(key: str):
    nov, ch, scene = SCENES[key]
    proj = sba.build_projection(nov, ch, scene)
    return sba.select_character_record(proj, scene)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def human_obs(char: str, sha: str, **over):
    """A qualified supplied HUMAN_REVIEW observation record (fixture)."""
    o = {
        "method": "HUMAN_REVIEW",
        "reviewer": "fixture-reviewer",
        "image_sha256": sha,
        "character_id": char,
        "face_readable": True,
        "view": "front",
        "face": {"status": "MATCH", "observed": "consistent with identity direction"},
        "hair": {"status": "MATCH", "observed": "canon hair"},
        "build": {"status": "MATCH", "observed": "canon build"},
        "age": {"status": "MATCH", "observed": "canon age presentation"},
        "eyes": {"status": "MATCH", "observed": "canon eyes"},
        "distinctive": {"status": "MATCH", "observed": "n/a"},
    }
    if char == "jarek":
        o["sex"] = {"status": "MATCH", "observed": "male"}
    o.update(over)
    return o


class _GateCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.log = self.tmp / "identity_observability.jsonl"

    def tearDown(self):
        self._td.cleanup()

    def img(self, name="out.png", data=b"\x89PNG\r\n\x1a\n" + b"fixture-bytes" * 200):
        p = self.tmp / name
        p.write_bytes(data)
        return p

    def gate(self, img, **kw):
        kw.setdefault("log_path", self.log)
        return ip.run_identity_acceptance_gate(img, path_id="TEST", **kw)

    def assert_not_accepted(self, res, img, decision=None):
        self.assertFalse(res.auto_accept_allowed)
        self.assertTrue(res.human_review_required)
        if decision:
            self.assertEqual(res.decision, decision)
        self.assertNotEqual(res.decision, "PASS")
        self.assertFalse(img.exists(), "blocked image must leave its publish location")
        self.assertTrue(Path(res.quarantine_path).exists())


# ---------------------------------------------------------------------------
# Part L boundary tests (flag ON unless stated)
# ---------------------------------------------------------------------------
class TestL01KaiValid(_GateCase):
    def test_kai_valid_pass_only_with_supplied_review_else_reject_review(self):
        with flag(True):
            spec = adapter_spec("kai")
            img = self.img()
            before = img.read_bytes()
            res = self.gate(img, spec=spec, novel="ha")
            self.assert_not_accepted(res, img, "REJECT_REVIEW")
            self.assertIn("HUMAN_REVIEW_OBSERVATIONS_ABSENT", res.fail_reason)
            self.assertEqual(Path(res.quarantine_path).read_bytes(), before)  # no byte mutation
            img2 = self.img("out2.png")
            res2 = self.gate(img2, spec=spec, novel="ha", observations=human_obs("kai", _sha(img2)))
            self.assertEqual(res2.decision, "PASS")
            self.assertTrue(res2.auto_accept_allowed)
            self.assertTrue(img2.exists())
            self.assertEqual(res2.records[0]["FACE_MATCH"]["method"], "HUMAN_REVIEW")


class TestL02KaiFaceDrift(_GateCase):
    def test_kai_face_drift_reject_review(self):
        with flag(True):
            img = self.img()
            obs = human_obs("kai", _sha(img), face={"status": "MATERIAL_DRIFT", "observed": "different face"})
            res = self.gate(img, spec=adapter_spec("kai"), novel="ha", observations=obs)
            self.assert_not_accepted(res, img, "REJECT_REVIEW")
            self.assertIn("FACE_DRIFT_VS_IDENTITY_DIRECTION", res.fail_reason)


class TestL03KaelValid(_GateCase):
    def test_kael_valid(self):
        with flag(True):
            spec = adapter_spec("kael_veyra")
            self.assertEqual(spec.identity.character_id, "kael_veyra")
            img = self.img()
            res = self.gate(img, spec=spec, novel="en", observations=human_obs("kael_veyra", _sha(img)))
            self.assertEqual(res.decision, "PASS", res.fail_reason)
            img2 = self.img("b.png")
            self.assert_not_accepted(self.gate(img2, spec=spec, novel="en"), img2, "REJECT_REVIEW")


class TestL04KaelEyeLighting(_GateCase):
    def test_kael_ambiguous_eye_under_colored_lighting_not_definite_violation(self):
        with flag(True):
            img = self.img()
            obs = human_obs("kael_veyra", _sha(img), eyes={"status": "MISMATCH", "observed": "magenta under neon"},
                            lighting_confound=True)
            res = self.gate(img, spec=adapter_spec("kael_veyra"), novel="en", observations=obs)
            self.assertIn(res.decision, ("REJECT_REVIEW", "FAIL_CLOSED"))
            self.assert_not_accepted(res, img)
            self.assertIn("EYE_COLOR_AMBIGUOUS_LIGHTING_CONFOUND", res.fail_reason)
            self.assertNotIn("EYE_COLOR_DRIFT", res.fail_reason)
            self.assertIn("AMBIGUOUS_NO_DEFINITE_VIOLATION", res.fail_reason)


class TestL05LiangAlternatePresentation(_GateCase):
    def test_liang_alternate_presentation_unspecified_ok(self):
        with flag(True):
            img = self.img()
            obs = human_obs("liang", _sha(img), unspecified_variance=["sex/gender presentation differs from milestone"])
            obs.pop("eyes")
            res = self.gate(img, spec=adapter_spec("liang"), novel="hp", observations=obs)
            self.assertEqual(res.decision, "UNSPECIFIED_OK", res.fail_reason)
            self.assertTrue(res.auto_accept_allowed)
            rec = res.records[0]
            self.assertEqual(rec["FINAL_IDENTITY_CONSTRAINT"]["constraint"]["SEX"]["value"], None)
            self.assertEqual(rec["FINAL_IDENTITY_CONSTRAINT"]["constraint"]["SEX"]["source"], "UNSPECIFIED")


class TestL06LiangPronouns(unittest.TestCase):
    def test_liang_pronouns_do_not_populate_canon(self):
        with flag(True):
            for key in ("liang_she", "liang_he", "liang"):
                rec = record_for(key)
                self.assertEqual(rec.gender, "", key)
                spec = adapter_spec(key)
                self.assertIn("SEX", spec.identity.unspecified_fields)
                blob = json.dumps(gs._to_jsonable(spec.identity)).lower()
                self.assertNotIn("female", blob)
                self.assertNotRegex(blob, r"\bmale\b")
                import visual_director as vd
                nov, _, scene = SCENES[key]
                pkg = vd.build_visual_scene_package(nov, "", scene, shots_text=[scene])
                for p in pkg.get("image_prompts") or []:
                    self.assertNotIn("Gender:", str(p))

    def test_pronouns_still_allowed_in_prose(self):
        with flag(True):
            nov, ch, scene = SCENES["liang_she"]
            d = sba.derive_spec_inputs(sba.build_projection(nov, ch, scene), scene)
            self.assertIsInstance(d, dict)  # prose containing pronouns is not rejected


class TestL07JarekAge16(unittest.TestCase):
    def test_jarek_age_16_reaches_spec(self):
        with flag(True):
            self.assertEqual(ip.GOVERNED_IDENTITY_CONTRACTS["jarek"].age_required, "16")
            spec = adapter_spec("jarek")
            self.assertEqual(spec.identity.age_required, "16")
            self.assertEqual(spec.identity.authority_source, "TEXT_CANON")
            self.assertIn("age 16", spec.composition.focal_point)
            self.assertEqual(record_for("jarek").age, "16")
            import visual_director as vd
            nov, _, scene = SCENES["jarek"]
            pkg = vd.build_visual_scene_package(nov, "", scene, shots_text=[scene])
            joined = "\n".join(str(p) for p in pkg.get("image_prompts") or [])
            self.assertIn("Age: 16", joined)
            self.assertNotIn("young adult", joined)


class TestL08JarekDrift(_GateCase):
    def test_jarek_age_build_drift_reject_review(self):
        with flag(True):
            img = self.img()
            obs = human_obs("jarek", _sha(img), age={"status": "MISMATCH", "observed": "adult ~30"},
                            build={"status": "MISMATCH", "observed": "heavily muscular"})
            res = self.gate(img, spec=adapter_spec("jarek"), novel="sf", observations=obs)
            self.assert_not_accepted(res, img, "REJECT_REVIEW")
            self.assertIn("AGE_DRIFT", res.fail_reason)
            self.assertIn("BUILD_DRIFT", res.fail_reason)
            self.assertEqual(res.records[0]["AGE_EXPECTED"], "16")
            self.assertEqual(res.records[0]["AGE_OBSERVED"], "adult ~30")


class TestL09L10JarekPlaceholders(_GateCase):
    def test_jarek_placeholder_hair_color_change_no_violation(self):
        with flag(True):
            img = self.img()
            obs = human_obs("jarek", _sha(img), hair={"status": "MATCH", "observed": "unkempt wild, blond"},
                            hair_color_observed="blond")
            res = self.gate(img, spec=adapter_spec("jarek"), novel="sf", observations=obs)
            self.assertEqual(res.decision, "PASS", res.fail_reason)
            self.assertIn("HAIR_COLOR", ip.GOVERNED_IDENTITY_CONTRACTS["jarek"].noncanon_placeholders)

    def test_jarek_skin_change_no_violation(self):
        with flag(True):
            img = self.img()
            obs = human_obs("jarek", _sha(img), skin_observed="dark brown")
            res = self.gate(img, spec=adapter_spec("jarek"), novel="sf", observations=obs)
            self.assertEqual(res.decision, "PASS", res.fail_reason)
            self.assertIn("SKIN", ip.GOVERNED_IDENTITY_CONTRACTS["jarek"].noncanon_placeholders)


class TestL11L12MilestoneOversteer(_GateCase):
    def test_milestone_sex_gender_oversteer_blocked(self):
        c = ip.GOVERNED_IDENTITY_CONTRACTS["liang"]
        r = ip.resolve_identity_constraint(c, milestone_proposals=[("SEX", "female", "milestone pixels")])
        self.assertIsNone(r["FINAL_IDENTITY_CONSTRAINT"]["SEX"]["value"])
        self.assertEqual(r["BLOCKED_PROPOSALS"][0]["decision"], "BLOCKED")
        self.assertEqual(r["BLOCKED_PROPOSALS"][0]["reason"], "UNSPECIFIED_STAYS_UNSPECIFIED")
        self.assertFalse(r["MILESTONE_CREATES_CANON"])
        with flag(True):  # a spec where Liang's unspecified field got filled fails closed
            spec = adapter_spec("liang")
            forged = dataclasses.replace(spec, identity=dataclasses.replace(spec.identity, eye_color_required="green"))
            img = self.img()
            res = self.gate(img, spec=forged, novel="hp")
            self.assert_not_accepted(res, img, "FAIL_CLOSED")

    def test_milestone_build_oversteer_blocked(self):
        c = ip.GOVERNED_IDENTITY_CONTRACTS["kai"]
        r = ip.resolve_identity_constraint(c, milestone_proposals=[("BUILD", "athletic", "milestone pixels")])
        self.assertEqual(r["FINAL_IDENTITY_CONSTRAINT"]["BUILD"]["value"], c.build_required)
        self.assertEqual(r["BLOCKED_PROPOSALS"][0]["reason"], "TEXT_CANON_WINS")
        with flag(True):
            img = self.img()
            obs = human_obs("kai", _sha(img), build={"status": "MISMATCH", "observed": "athletic (milestone-like)"})
            res = self.gate(img, spec=adapter_spec("kai"), novel="ha", observations=obs)
            self.assert_not_accepted(res, img, "REJECT_REVIEW")
            self.assertIn("BUILD_DRIFT", res.fail_reason)


class TestL13CrossCharacter(_GateCase):
    def test_cross_character_route_fail_closed(self):
        with flag(True):
            img = self.img()
            res = self.gate(img, spec=adapter_spec("kai"), novel="en")  # Kai spec routed to Eternal Nexus
            self.assert_not_accepted(res, img, "FAIL_CLOSED")
            self.assertIn("ROUTING_NOVEL_MATCHES_CONTRACT", res.fail_reason)
            kai = adapter_spec("kai")
            kael_fields = ip.identity_spec_fields(ip.GOVERNED_IDENTITY_CONTRACTS["kael_veyra"])
            kael_fields["character_id"] = "kai"
            forged = dataclasses.replace(kai, identity=dataclasses.replace(kai.identity, **kael_fields))
            img2 = self.img("b.png")
            res2 = self.gate(img2, spec=forged, novel="ha")
            self.assert_not_accepted(res2, img2, "FAIL_CLOSED")
            img3 = self.img("c.png")
            res3 = self.gate(img3, spec=adapter_spec("kai"), novel="ha", character_id="jarek")
            self.assert_not_accepted(res3, img3, "FAIL_CLOSED")


class TestL14RearView(_GateCase):
    def test_uncertain_rear_view_fail_closed(self):
        with flag(True):
            img = self.img()
            obs = human_obs("kai", _sha(img), face_readable=False, view="rear")
            res = self.gate(img, spec=adapter_spec("kai"), novel="ha", observations=obs)
            self.assert_not_accepted(res, img, "FAIL_CLOSED")
            self.assertIn("FACE_NOT_READABLE_IDENTITY_UNVERIFIABLE", res.fail_reason)


class TestL15L16WardrobeEffectSubstitution(_GateCase):
    def _decisions(self, mutate_spec, extra_obs):
        with flag(True):
            spec = adapter_spec("kai")
            a = self.img("a.png")
            ra = self.gate(a, spec=spec, novel="ha", observations=human_obs("kai", _sha(a)))
            b = self.img("b.png")
            rb = self.gate(b, spec=mutate_spec(spec), novel="ha", observations=human_obs("kai", _sha(b), **extra_obs))
            c = self.img("c.png")
            rc = self.gate(c, spec=spec, novel="ha")
            d = self.img("d.png")
            rd = self.gate(d, spec=mutate_spec(spec), novel="ha")
            return ra, rb, rc, rd

    def test_wardrobe_substitution_does_not_change_decision(self):
        def mut(spec):
            w = spec.wardrobe
            if dataclasses.is_dataclass(w):
                flds = {f.name for f in dataclasses.fields(w)}
                ch = {}
                for n in flds:
                    v = getattr(w, n)
                    if isinstance(v, str):
                        ch[n] = "bright red leather jacket"
                    elif isinstance(v, tuple) and all(isinstance(x, str) for x in v):
                        ch[n] = ("bright red leather jacket",)
                if ch:
                    w = dataclasses.replace(w, **ch)
            return dataclasses.replace(spec, wardrobe=w)
        ra, rb, rc, rd = self._decisions(mut, {"wardrobe_observed": "red leather jacket"})
        self.assertEqual(ra.decision, rb.decision)
        self.assertEqual(ra.decision, "PASS")
        self.assertEqual(rc.decision, rd.decision)

    def test_effect_substitution_does_not_change_decision(self):
        def mut(spec):
            c = spec.content
            return dataclasses.replace(spec, content=dataclasses.replace(
                c, narrative_intent="violet lightning aura and holo UI everywhere"))
        ra, rb, rc, rd = self._decisions(mut, {"effects_observed": "violet lightning"})
        self.assertEqual(ra.decision, rb.decision)
        self.assertEqual(rc.decision, rd.decision)


def _realistic_held(key):
    from tools import realistic_pipeline_v2 as rp
    nov, ch, scene = SCENES[key]
    scene = scene + " Holding the blade."
    return rp, rp.build_realistic_generation_spec(novel=nov, chapter=ch, scene_text=scene, prompt=scene)


def _has_ipadapter(workflow) -> bool:
    return any("IPAdapter" in str(n.get("class_type", "")) for n in (workflow or {}).values() if isinstance(n, dict))


class TestL17L18MilestoneConditioning(_GateCase):
    def test_whole_milestone_conditioning_blocked_on(self):
        with flag(True):
            for key in ("kai", "kael_veyra", "liang", "jarek"):
                rp, spec = _realistic_held(key)
                self.assertEqual(tuple(spec.references.style_refs), (), key)
                self.assertTrue(spec.identity.milestone_reference_id, key)  # audit ref kept
                r = rp.run_realistic_resolution(spec)
                self.assertFalse(_has_ipadapter(r.workflow), key)
        rec = sba.retrieve_milestone_visual_reference("ha", "kai")
        self.assertIsNotNone(rec)  # milestone record not deleted; remains audit/visual-direction ref

    def test_style_ref_experimental_cannot_bypass(self):
        with flag(False):
            rp, legacy_spec = _realistic_held("kai")  # legacy spec still carries the milestone style_ref
        with flag(True, STYLE_REF_EXPERIMENTAL="1", STYLE_REF_STRENGTH="0.6"):
            with mock.patch.object(rp, "_stage_style_ref_for_comfy", side_effect=AssertionError("must not stage")):
                r = rp.run_realistic_resolution(legacy_spec)
                self.assertFalse(_has_ipadapter(r.workflow))
                self.assertNotEqual(str(r.provenance.get("STYLE_REF_CONDITIONING_ACTIVE", "NO")).upper(), "YES")
            img = self.img()
            res = self.gate(img, spec=legacy_spec, novel="ha", milestone_conditioning_used=True)
            self.assert_not_accepted(res, img, "FAIL_CLOSED")
            self.assertIn("MILESTONE", res.fail_reason)


class TestL19LoggerFailure(_GateCase):
    def test_logger_failure_blocks_acceptance(self):
        with flag(True):
            img = self.img()

            def boom(*a, **k):
                raise OSError("disk full")
            res = self.gate(img, spec=adapter_spec("kai"), novel="ha",
                            observations=human_obs("kai", _sha(img)), writer=boom)
            self.assert_not_accepted(res, img, "FAIL_CLOSED")
            self.assertIn("OBSERVABILITY_LOG_FAILURE", res.fail_reason)
            with self.assertRaises(ip.IdentityAcceptanceBlocked):
                img2 = self.img("b.png")
                ip.enforce_identity_acceptance(img2, path_id="TEST", spec=adapter_spec("kai"), novel="ha",
                                               observations=human_obs("kai", _sha(img2)), writer=boom,
                                               log_path=self.log)


class TestL20FeatureOffLegacy(_GateCase):
    def test_feature_off_restores_legacy(self):
        with flag(False):
            off_specs = {k: gs.generation_spec_sha256(adapter_spec(k)) for k in ("kai", "kael_veyra", "liang", "jarek")}
            off_rec = record_for("liang_she")
            off_lock = sba.identity_lock_phrase(record_for("kai"))
        with flag(True):
            on_specs = {k: gs.generation_spec_sha256(adapter_spec(k)) for k in off_specs}
        with flag(False):
            back = {k: gs.generation_spec_sha256(adapter_spec(k)) for k in off_specs}
            spec = adapter_spec("kai")
            self.assertEqual(spec.identity.contract_id, "")
            self.assertNotIn("contract_id", json.dumps(gs._to_jsonable(spec.identity)))
            img = self.img()
            res = self.gate(img, spec=spec, novel="ha")
            self.assertEqual(res.decision, "BYPASS")
            self.assertTrue(res.auto_accept_allowed)
            self.assertTrue(img.exists())
            self.assertFalse(self.log.exists())
            self.assertEqual(off_rec.gender, record_for("liang_she").gender)  # legacy pronoun path intact under OFF
            self.assertIn("gray shirt", off_lock)
        self.assertEqual(off_specs, back)
        self.assertNotEqual(off_specs, on_specs)


# ---------------------------------------------------------------------------
# Contracts / spec / lock / flag / observability / rollback
# ---------------------------------------------------------------------------
class TestContracts(unittest.TestCase):
    def test_four_governed_contracts(self):
        self.assertEqual(set(ip.list_governed_character_keys()), {"kai", "kael_veyra", "liang", "jarek"})
        for c in ip.GOVERNED_IDENTITY_CONTRACTS.values():
            self.assertEqual(ip.IDENTITY_AUTHORITY_SOURCE, "TEXT_CANON")
            self.assertTrue(c.contract_id)
        self.assertEqual(ip.CANON_PRECEDENCE, ("TEXT_CANON", "VISUAL_DIRECTION", "MILESTONE_REFERENCE"))
        self.assertFalse(ip.MILESTONE_CREATES_CANON)
        self.assertEqual(ip.MILESTONE_IDENTITY_AUTHORITY_CREATED, "NO")

    def test_jarek_age_16_exact_and_sourced(self):
        j = ip.GOVERNED_IDENTITY_CONTRACTS["jarek"]
        self.assertEqual(j.age_required, "16")
        self.assertTrue(j.authority()["AGE"].startswith("TEXT_CANON"))
        self.assertIn("sixteen", ip.JAREK_AGE_SOURCE)
        self.assertIn("HAIR_COLOR", j.noncanon_placeholders)
        self.assertIn("SKIN", j.noncanon_placeholders)

    def test_liang_sex_unspecified(self):
        l = ip.GOVERNED_IDENTITY_CONTRACTS["liang"]
        self.assertFalse(l.sex)
        self.assertIn("SEX", l.unspecified_fields)
        self.assertEqual(ip.contract_sex_for_record("liang"), "")

    def test_no_prompt_binding_false_positive(self):
        self.assertEqual(ip.governed_characters_in_text("A kaiju in the lianghua market"), ())


class TestIdentitySpec(unittest.TestCase):
    NEW = ("novel_id", "contract_id", "age_required", "age_allowed", "build_required", "build_allowed",
           "face_direction", "hair_required", "hair_allowed", "eye_color_required", "eye_color_allowed",
           "distinctive_traits_required", "visual_direction_allowed", "unspecified_fields",
           "scene_dependent_fields", "identity_forbidden", "authority_source", "milestone_reference_id")

    def test_fields_present(self):
        names = {f.name for f in dataclasses.fields(gs.IdentitySpec)}
        for n in ("character_id",) + self.NEW:
            self.assertIn(n, names)

    def test_default_serialization_legacy(self):
        self.assertEqual(set(gs._to_jsonable(gs.IdentitySpec())), LEGACY_IDENTITY_KEYS)
        self.assertEqual(set(gs._to_jsonable(gs.IdentitySpec(character_id="kai"))), LEGACY_IDENTITY_KEYS)

    def test_populated_requires_text_canon(self):
        with flag(True):
            _rp, spec = _realistic_held("kai")  # real realistic V2 spec (asset SHAs resolved on DavidsPC)
        gs.validate_generation_spec(spec)  # populated + TEXT_CANON validates
        bad = dataclasses.replace(spec, identity=dataclasses.replace(spec.identity, authority_source="MILESTONE_REFERENCE"))
        with self.assertRaises(gs.GenerationSpecValidationError) as cm:
            gs.validate_generation_spec(bad)
        self.assertIn("identity.authority_source", str(cm.exception))


class TestIdentityOnlyLock(unittest.TestCase):
    def test_on_locks_identity_only_denylist(self):
        with flag(True):
            for key in ("kai", "kael_veyra", "liang", "jarek"):
                nov, ch, scene = SCENES[key]
                d = sba.derive_spec_inputs(sba.build_projection(nov, ch, scene), scene)
                lock = adapter_spec(key).composition.focal_point
                self.assertEqual(ip.identity_lock_denylist_hits(lock), [], (key, lock))
                self.assertTrue(lock)
                self.assertIn("non_identity_descriptors", d)

    def test_wardrobe_effect_terms_go_to_own_domains(self):
        with flag(True):
            spec = adapter_spec("kai")
            self.assertIn("gray shirt", spec.content.narrative_intent)  # preserved in content domain
            self.assertNotIn("shirt", spec.composition.focal_point)

    def test_denylist_catches_legacy(self):
        with flag(False):
            legacy = sba.identity_lock_phrase(record_for("kai"))
        self.assertTrue(ip.identity_lock_denylist_hits(legacy))


class TestVerifierPolicy(_GateCase):
    def test_no_observations_never_pass(self):
        with flag(True):
            for key, nov in (("kai", "ha"), ("kael_veyra", "en"), ("liang", "hp"), ("jarek", "sf")):
                img = self.img(f"{key}.png")
                res = self.gate(img, spec=adapter_spec(key), novel=nov)
                self.assertEqual(res.decision, "REJECT_REVIEW", (key, res.fail_reason))
                self.assertEqual(res.records[0]["HUMAN_REVIEW_REQUIRED"], "YES")
                self.assertTrue(res.records[0]["AUTOMATED_EVIDENCE_AVAILABLE"].startswith("NO"))

    def test_unqualified_method_not_pass(self):
        with flag(True):
            img = self.img()
            res = self.gate(img, spec=adapter_spec("kai"), novel="ha",
                            observations=human_obs("kai", _sha(img), method="AUTOMATED_HEURISTIC"))
            self.assertEqual(res.decision, "REJECT_REVIEW")

    def test_observation_sha_mismatch_fail_closed(self):
        with flag(True):
            img = self.img()
            res = self.gate(img, spec=adapter_spec("kai"), novel="ha", observations=human_obs("kai", "0" * 64))
            self.assertEqual(res.decision, "FAIL_CLOSED")

    def test_non_governed_prompt_not_applicable_but_logged(self):
        with flag(True):
            img = self.img()
            res = self.gate(img, prompt="a misty mountain landscape at dawn")
            self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
            self.assertTrue(img.exists())
            self.assertTrue(self.log.exists())

    def test_prompt_binding_v1(self):
        with flag(True):
            img = self.img()
            res = self.gate(img, prompt="Jarek in the forge, cinematic")
            self.assertEqual(res.decision, "REJECT_REVIEW")
            self.assertEqual(res.records[0]["CHARACTER"], "jarek")

    def test_v1_novel_title_protagonist_fallback_binding(self):
        with flag(True):
            img = self.img()
            res = self.gate(img, prompt="Social promo artwork for Soul Forge Era. A figure in the undercity.")
            self.assertEqual(res.decision, "REJECT_REVIEW")
            self.assertEqual(res.records[0]["CHARACTER"], "jarek")
            self.assertEqual(res.records[0]["BINDING_METHOD"], "NOVEL_PROTAGONIST_FALLBACK")
            img2 = self.img("b.png")
            res2 = self.gate(img2, prompt="Kai under the System HUD, Heavenly Ascension System")
            self.assertEqual(res2.records[0]["BINDING_METHOD"], "PROMPT_GOVERNED_NAME")
            self.assertEqual(len(res2.records), 1)

    def test_human_review_release_restores_bytes_unchanged(self):
        with flag(True):
            img = self.img()
            before = img.read_bytes()
            res = self.gate(img, spec=adapter_spec("kai"), novel="ha")
            q = Path(res.quarantine_path)
            rel = ip.review_quarantined_image(q, human_obs("kai", _sha(q)), character_id="kai", novel="ha",
                                              spec=adapter_spec("kai"), log_path=self.log)
            self.assertEqual(rel.decision, "PASS")
            self.assertTrue(img.exists())
            self.assertEqual(img.read_bytes(), before)


class TestObservability(_GateCase):
    def test_record_complete(self):
        with flag(True):
            img = self.img()
            res = self.gate(img, spec=adapter_spec("jarek"), novel="sf")
            lines = [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertTrue(lines)
            for f in ip.REQUIRED_LOG_FIELDS:
                self.assertIn(f, lines[-1], f)
            self.assertEqual(ip.validate_observability_record(lines[-1]), [])
            r = lines[-1]
            self.assertEqual(r["AUTHORITY_SOURCE"], "TEXT_CANON")
            self.assertEqual(r["AGE_EXPECTED"], "16")
            self.assertEqual(r["MILESTONE_CONDITIONING_USED"], "NO")
            self.assertEqual(r["FEATURE_FLAG_ENABLED"], "YES")
            self.assertEqual(r["AUTO_ACCEPT_ALLOWED"], "NO")
            side = Path(res.quarantine_path + ".identity_preservation.json")
            self.assertTrue(side.exists())


class TestFlag(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(ip.is_identity_preservation_enabled({}))
        for v in ("", "0", "false", "no", "off", "maybe"):
            self.assertFalse(ip.is_identity_preservation_enabled({FLAG: v}), v)
        for v in ("1", "true", "YES", "on"):
            self.assertTrue(ip.is_identity_preservation_enabled({FLAG: v}), v)
        self.assertEqual(ip.PRODUCTION_DEFAULT, "NO")

    def test_isolated_from_wardrobe(self):
        from tools import wardrobe_preservation as wp
        self.assertFalse(ip.is_identity_preservation_enabled({"ENABLE_WARDROBE_PRESERVATION": "1"}))
        self.assertTrue(wp.is_wardrobe_preservation_enabled({"ENABLE_WARDROBE_PRESERVATION": "1"}))
        self.assertFalse(wp.is_wardrobe_preservation_enabled({FLAG: "1"}))
        with flag(False):
            w_off = gs._to_jsonable(adapter_spec("kai").wardrobe)
        with flag(True):
            w_on = gs._to_jsonable(adapter_spec("kai").wardrobe)
        self.assertEqual(w_off, w_on)  # identity flag does not change wardrobe domain
        self.assertIn("WARDROBE", ip.SCOPE_EXCLUSIONS)
        self.assertIn("HELD_PROP", ip.SCOPE_EXCLUSIONS)


class TestRollback(_GateCase):
    def test_on_to_off_immediate(self):
        with flag(True):
            on_lock = adapter_spec("jarek").composition.focal_point
        with flag(False):
            off_spec = adapter_spec("jarek")
            self.assertNotIn("age 16", off_spec.composition.focal_point)
            self.assertNotEqual(on_lock, off_spec.composition.focal_point)
            img = self.img()
            self.assertEqual(self.gate(img, spec=off_spec, novel="sf").decision, "BYPASS")



# ---------------------------------------------------------------------------
# LOCAL_SDXL_RESTRICT_PROTAGONIST_FALLBACK_IMPLEMENTATION (Stage-1) — 9 cases
# Portable CPU fixtures: sealed governed novel/character IDs only (structural
# fields; no Studio Bible profile/canon prose). Linux-CI safe without private trees.
# ---------------------------------------------------------------------------

# Structural INTENT_YES fixture (character_id / novel_id / path_id only).
SYNTHETIC_INTENT_YES_FIXTURE = {
    "novel_id": "ha",
    "character_id": "kai",
    "path_id": "V1:local_stable_diffusion",
}


class TestLocalSdxlRestrictProtagonistFallback(_GateCase):
    """PATH_ID V1:local_stable_diffusion: restrict novel-only protagonist fallback."""

    LOCAL = "V1:local_stable_diffusion"

    def gate_local(self, img, **kw):
        kw.setdefault("log_path", self.log)
        kw.setdefault("use_ambient_context", False)
        return ip.run_identity_acceptance_gate(img, path_id=self.LOCAL, **kw)

    def test_01_intent_no_skips_novel_protagonist_fallback(self):
        with flag(True):
            img = self.img("intent_no.png")
            ctx = ip.IdentityProductionContext(novel_id="ha")
            res = self.gate_local(img, novel="ha", identity_context=ctx)
            self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
            self.assertTrue(img.exists())
            r = res.records[0]
            self.assertEqual(r.get("CHARACTER") or "", "")
            self.assertNotEqual(r.get("BINDING_METHOD"), "NOVEL_PROTAGONIST_FALLBACK")
            self.assertEqual(r["UPSTREAM_CHARACTER_ASSIGNED"], "NO")
            self.assertEqual(r["IDENTITY_GATE_REQUIRED"], "NO")
            self.assertIn(
                "NOVEL_PROTAGONIST_FALLBACK_RESTRICTED:UPSTREAM_CHARACTER_ASSIGNED=NO",
                r.get("NO_GOVERNED_CHARACTER_REASON") or "",
            )

    def test_02_intent_yes_explicit_character_preserved(self):
        with flag(True):
            img = self.img("intent_yes_explicit.png")
            fx = SYNTHETIC_INTENT_YES_FIXTURE
            ctx = ip.IdentityProductionContext(novel_id=fx["novel_id"])
            res = self.gate_local(
                img, novel=fx["novel_id"], character_id=fx["character_id"], identity_context=ctx)
            self.assertEqual(res.decision, "REJECT_REVIEW")
            r = res.records[0]
            self.assertEqual(r["CHARACTER"], fx["character_id"])
            self.assertEqual(r["UPSTREAM_CHARACTER_ASSIGNED"], "YES")
            self.assertEqual(r["CHARACTER_BINDING_SOURCE"], "STRUCTURED_CHARACTER_ID")
            self.assertNotEqual(r.get("BINDING_METHOD"), "NOVEL_PROTAGONIST_FALLBACK")
            self.assertEqual(r["IDENTITY_GATE_REQUIRED"], "YES")

    def test_03_intent_unknown_fail_closed_no_new_fallback(self):
        # Gate always supplies bool when restrict is on; UNKNOWN is the resolve seam
        # when upstream_character_assigned is missing/None under restriction.
        ctx = ip.IdentityProductionContext(novel_id="hp")
        br = ip.resolve_governed_binding(
            novel="hp",
            context=ctx,
            apply_novel_protagonist_fallback_restriction=True,
            upstream_character_assigned=None,
        )
        self.assertEqual(br.result, "FAILED")
        self.assertIn(
            "FAIL_CLOSED_NO_NEW_PROTAGONIST_FALLBACK:UPSTREAM_CHARACTER_ASSIGNED_UNKNOWN",
            br.fail_reason or "",
        )
        self.assertEqual(br.keys, [])

    def test_04_intent_yes_depicted_characters_preserved(self):
        with flag(True):
            img = self.img("intent_yes_depicted.png")
            ctx = ip.IdentityProductionContext(novel_id="hp")
            intent = ip.ImageIntentRequest(depicted_characters=("liang",))
            res = self.gate_local(
                img, novel="hp", identity_context=ctx, image_intent=intent)
            self.assertEqual(res.decision, "REJECT_REVIEW")
            r = res.records[0]
            self.assertEqual(r["CHARACTER"], "liang")
            self.assertEqual(r["UPSTREAM_CHARACTER_ASSIGNED"], "YES")
            self.assertNotEqual(r.get("BINDING_METHOD"), "NOVEL_PROTAGONIST_FALLBACK")

    def test_05_test_path_keeps_novel_protagonist_fallback(self):
        with flag(True):
            img = self.img("test_path_legacy.png")
            ctx = ip.IdentityProductionContext(novel_id="ha")
            res = self.gate(img, novel="ha", identity_context=ctx, use_ambient_context=False)
            self.assertEqual(res.decision, "REJECT_REVIEW")
            r = res.records[0]
            self.assertEqual(r["CHARACTER"], "kai")
            self.assertEqual(r["BINDING_METHOD"], "NOVEL_PROTAGONIST_FALLBACK")

    def test_06_v2_path_keeps_novel_protagonist_fallback(self):
        with flag(True):
            img = self.img("v2_path.png")
            ctx = ip.IdentityProductionContext(novel_id="ha")
            res = ip.run_identity_acceptance_gate(
                img, path_id="V2:realistic:generate_promo_image_v2", novel="ha",
                identity_context=ctx, log_path=self.log, use_ambient_context=False)
            self.assertEqual(res.decision, "REJECT_REVIEW")
            r = res.records[0]
            self.assertEqual(r["CHARACTER"], "kai")
            self.assertEqual(r["BINDING_METHOD"], "NOVEL_PROTAGONIST_FALLBACK")

    def test_07_openai_path_keeps_novel_protagonist_fallback(self):
        with flag(True):
            img = self.img("openai_path.png")
            ctx = ip.IdentityProductionContext(novel_id="en")
            res = ip.run_identity_acceptance_gate(
                img, path_id="V1:openai", novel="en",
                identity_context=ctx, log_path=self.log, use_ambient_context=False)
            self.assertEqual(res.decision, "REJECT_REVIEW")
            r = res.records[0]
            self.assertEqual(r["CHARACTER"], "kael_veyra")
            self.assertEqual(r["BINDING_METHOD"], "NOVEL_PROTAGONIST_FALLBACK")

    def test_08_intent_yes_via_context_character_id(self):
        with flag(True):
            img = self.img("intent_yes_ctx.png")
            ctx = ip.IdentityProductionContext(novel_id="sf", character_id="jarek")
            res = self.gate_local(img, novel="sf", identity_context=ctx)
            self.assertEqual(res.decision, "REJECT_REVIEW")
            r = res.records[0]
            self.assertEqual(r["CHARACTER"], "jarek")
            self.assertEqual(r["UPSTREAM_CHARACTER_ASSIGNED"], "YES")
            self.assertEqual(r["CHARACTER_BINDING_SOURCE"], "STRUCTURED_CHARACTER_ID")

    def test_09_intent_no_alias_only_no_false_identity_review(self):
        with flag(True):
            img = self.img("intent_no_alias.png")
            ctx = ip.IdentityProductionContext(novel_abbreviation="HP")
            res = self.gate_local(img, identity_context=ctx)
            self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
            self.assertTrue(img.exists())
            r = res.records[0]
            self.assertEqual(r.get("CHARACTER") or "", "")
            self.assertEqual(r["UPSTREAM_CHARACTER_ASSIGNED"], "NO")
            self.assertEqual(r["IDENTITY_GATE_REQUIRED"], "NO")
            self.assertEqual(r["AUTO_ACCEPT_ALLOWED"], "YES")
            self.assertIn("NOVEL_PROTAGONIST_FALLBACK_RESTRICTED", r.get("NO_GOVERNED_CHARACTER_REASON") or "")



if __name__ == "__main__":
    unittest.main()
