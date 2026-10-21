# -*- coding: utf-8 -*-
"""IDENTITY_FINAL_COVERAGE_HARDENING_20260930 - Part M tests (A-T + extras).

CPU only, GPU_GENERATIONS=0: no provider is ever called (the identity gate is driven directly
on synthetic bytes; promo_builder collaborators are stubs; the Visual Director only builds text).
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import promo_builder as pb  # noqa: E402
import visual_director as vd  # noqa: E402
from tools import identity_preservation as ip  # noqa: E402

FLAG = "ENABLE_IDENTITY_PRESERVATION"
FAKE = b"\x89PNG\r\n\x1a\n" + b"FINAL-HARDENING-FAKE" * 120


@contextlib.contextmanager
def identity_flag(on: bool, log_path: Path):
    saved = {k: os.environ.get(k) for k in (FLAG, "IDENTITY_OBSERVABILITY_LOG", "STYLE_REF_EXPERIMENTAL", "AIVSB_REASONING_ENABLED")}
    os.environ.pop(FLAG, None)
    os.environ.pop("STYLE_REF_EXPERIMENTAL", None)
    # AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: these suites qualify the NON-AIVSB rules; keep them
    # hermetic (the user env sets AIVSB on, which now makes provenance-less governed scenery review).
    os.environ["AIVSB_REASONING_ENABLED"] = "off"
    os.environ["IDENTITY_OBSERVABILITY_LOG"] = str(log_path)
    if on:
        os.environ[FLAG] = "1"
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.log = self.tmp / "identity_observability.jsonl"
        self._n = 0

    def tearDown(self):
        self._td.cleanup()

    def img(self, name: str = "", data: bytes = b"") -> Path:
        self._n += 1
        p = self.tmp / (name or f"img{self._n}.png")
        p.write_bytes(data or (FAKE + str(self._n).encode()))
        return p

    def gate(self, img=None, **kw):
        kw.setdefault("quarantine", False)
        kw.setdefault("write_sidecar", False)
        kw.setdefault("path_id", "TEST:IFCH")
        with identity_flag(True, self.log):
            return ip.run_identity_acceptance_gate(img or self.img(), **kw)

    def logged(self):
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def assert_fail_closed_binding(self, res, *, malformed=None, conflict=None):
        self.assertEqual(res.decision, "FAIL_CLOSED")
        self.assertFalse(res.auto_accept_allowed)
        self.assertIn(ip.GOVERNED_CONTEXT_BINDING_FAILED, res.fail_reason)
        self.assertNotEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
        for r in res.records:
            self.assertEqual(r["GOVERNED_CONTEXT_BINDING_RESULT"], "FAILED")
            self.assertEqual(r["PROMPT_FALLBACK_USED"], "NO")
            self.assertEqual(r["AUTO_ACCEPT_ALLOWED"], "NO")
            self.assertEqual(r["IDENTITY_GATE_REQUIRED"], "YES")
            self.assertEqual(r["SCENERY_BYPASS_APPLIED"], "NO")
            self.assertTrue(r["BINDING_FAILURE_REASON"].startswith(ip.GOVERNED_CONTEXT_BINDING_FAILED))
            if malformed is not None:
                self.assertEqual(r["MALFORMED_CHARACTER_ID"], "YES" if malformed else "NO")
            if conflict is not None:
                self.assertEqual(r["STRUCTURED_CHARACTER_CONFLICT"], "YES" if conflict else "NO")
            self.assertEqual(ip.validate_observability_record(r), [])


# ---------------------------------------------------------------------------
# A-F: structured character validation / conflicts
# ---------------------------------------------------------------------------
class TestStructuredCharacter(_Base):
    def test_A_en_kaael_fail_closed(self):
        self.assert_fail_closed_binding(self.gate(novel="Eternal Nexus", character_id="kaael"), malformed=True)

    def test_B_sf_jarekk_fail_closed(self):
        self.assert_fail_closed_binding(self.gate(novel="SF", character_id="jarekk"), malformed=True)

    def test_C_ha_kia_fail_closed(self):
        self.assert_fail_closed_binding(self.gate(novel="HA", character_id="kia"), malformed=True)

    def test_D_hp_liagn_fail_closed(self):
        self.assert_fail_closed_binding(self.gate(novel="HP", character_id="liagn"), malformed=True)

    def test_D2_context_carrier_malformed_fail_closed(self):
        for abbr, cid in (("EN", "kaael"), ("SF", "jarekk"), ("HA", "kia"), ("HP", "liagn")):
            ctx = ip.build_identity_context(abbr=abbr, character_id=cid)
            self.assert_fail_closed_binding(self.gate(identity_context=ctx, prompt="a quiet scene"), malformed=True)

    def test_E_structured_novel_character_conflict_fail_closed(self):
        for novel, cid in (("Eternal Nexus", "jarek"), ("Soul Forge Era", "kael"), ("HP", "kai")):
            self.assert_fail_closed_binding(self.gate(novel=novel, character_id=cid), conflict=True)
        # prompt text naming the "right" character cannot repair the conflict
        self.assert_fail_closed_binding(self.gate(novel="Eternal Nexus", character_id="jarek",
                                                  prompt="Kael Veyra logs in"), conflict=True)
        # a structured depicted character from another novel conflicts too
        self.assert_fail_closed_binding(self.gate(novel="HP", prompt="x",
                                                  image_intent={"depicted_characters": ["kai"]}), conflict=True)

    def test_F_prompt_names_correct_character_but_structured_id_malformed(self):
        for novel, cid, prompt in (("EN", "kaael", "Kael Veyra logs in"), ("SF", "jarekk", "Jarek climbs"),
                                   ("HA", "kia", "Kai walks"), ("HP", "liagn", "Liang meditates")):
            res = self.gate(novel=novel, character_id=cid, prompt=prompt)
            self.assert_fail_closed_binding(res, malformed=True)
            self.assertNotIn("PROMPT_GOVERNED_NAME_SUPPLEMENTAL", res.fail_reason)

    def test_valid_governed_ids_still_bind(self):
        for novel, cid, key in (("EN", "kael", "kael_veyra"), ("EN", "Kael Veyra", "kael_veyra"), ("SF", "jarek", "jarek"),
                                ("HA", "kai", "kai"), ("HP", "liang", "liang")):
            res = self.gate(novel=novel, character_id=cid, prompt="x")
            self.assertEqual(res.decision, "REJECT_REVIEW", (novel, cid))
            self.assertEqual(res.records[0]["CHARACTER"], key)
            self.assertEqual(res.records[0]["STRUCTURED_CHARACTER_VALID"], "YES_GOVERNED")
            self.assertEqual(res.records[0]["IDENTITY_GATE_EXECUTED"], "YES")

    def test_extra_sentinel_character_ids_fail_closed_in_governed_novel(self):
        for sentinel in ("scenery", "none", "environment", "no_character", "SCENERY_ONLY"):
            for novel in ("SF", "HP"):
                res = self.gate(novel=novel, character_id=sentinel, prompt="a quiet valley")
                self.assert_fail_closed_binding(res, malformed=True)

    def test_extra_sentinel_even_with_structured_scenery_intent_fail_closed(self):
        # a malformed structured id is never an escape, even when intent says scenery
        res = self.gate(novel="SF", character_id="scenery", prompt="a valley",
                        image_intent={"scene_subject": "scenery"})
        self.assert_fail_closed_binding(res, malformed=True)

    def test_extra_gray_non_governed_and_named_jarek_is_governed(self):
        res = self.gate(novel="SF", character_id="gray", prompt="a young smith hauls chains")
        self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
        r = res.records[0]
        self.assertEqual(r["IMAGE_INTENT_CLASS"], "NON_GOVERNED_CHARACTER_DEPICTION")
        self.assertEqual(r["STRUCTURED_CHARACTER_VALID"], "YES_NON_GOVERNED_CAST_MEMBER")
        self.assertEqual(r["IDENTITY_GATE_REQUIRED"], "NO")
        # Gray id + Jarek named in the prompt -> governed path (never accepted unverified)
        res = self.gate(novel="SF", character_id="gray", prompt="Jarek hauls chains beside Gray")
        self.assertFalse(res.auto_accept_allowed)
        self.assertEqual(res.records[0]["GOVERNED_CHARACTER_DEPICTION"], "YES")
        # Gray id + structured depicted Jarek -> governed wins (Part E)
        res = self.gate(novel="SF", character_id="gray", prompt="a smith",
                        image_intent={"depicted_characters": ["jarek"]})
        self.assertFalse(res.auto_accept_allowed)
        self.assertEqual(res.records[0]["IMAGE_INTENT_SOURCE"], "STRUCTURED_DEPICTED_CHARACTER")

    def test_extra_cast_matches_studio_bible(self):
        base = Path(os.environ.get("AIVSB_CHARACTERS_DIR", r"C:\Users\David\Documents\Inkblade Author Studio\scripts\aivsb\characters"))
        if not base.exists():
            self.skipTest("Studio Bible character profiles not present")
        import yaml
        found: dict = {}

        def walk(x):
            if isinstance(x, dict):
                if x.get("name") and x.get("novel"):
                    found.setdefault(str(x["novel"]).strip().lower(), set()).add(str(x["name"]).strip())
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        for f in base.glob("*.yaml"):
            walk(yaml.safe_load(f.read_text(encoding="utf-8")))
        for novel, names in ip.GOVERNED_NOVEL_CAST.items():
            for n in names:
                self.assertIn(n, found.get(novel, set()), (novel, n, found))
        # the four governed characters are cast members of their own novel
        for key, novel in (("kai", "ha"), ("kael_veyra", "en"), ("liang", "hp"), ("jarek", "sf")):
            self.assertIn(ip.GOVERNED_IDENTITY_CONTRACTS[key].display_name, ip.GOVERNED_NOVEL_CAST[novel])

# ---------------------------------------------------------------------------
# G-M: intent classification, scenery bypass, anti-spoof
# ---------------------------------------------------------------------------
class TestImageIntent(_Base):
    def assert_bypass(self, res, cls):
        self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
        self.assertTrue(res.auto_accept_allowed)
        r = res.records[0]
        self.assertEqual(r["IMAGE_INTENT_CLASS"], cls)
        self.assertEqual(r["SCENERY_BYPASS_APPLIED"], "YES")
        self.assertEqual(r["IDENTITY_GATE_REQUIRED"], "NO")
        self.assertEqual(r["GOVERNED_CHARACTER_DEPICTION"], "NO")
        self.assertEqual(r["CHARACTER"], "")
        self.assertEqual(r["GOVERNED_CONTEXT_BINDING_RESULT"], "NOT_REQUIRED_NON_DEPICTION_INTENT")
        self.assertTrue(r["SCENERY_BYPASS_REASON"].startswith("SCENERY_BYPASS:"))
        self.assertEqual(ip.validate_observability_record(r), [])

    def assert_governed_gate(self, res):
        self.assertFalse(res.auto_accept_allowed)
        r = res.records[0]
        self.assertEqual(r["GOVERNED_CHARACTER_DEPICTION"], "YES")
        self.assertEqual(r["IDENTITY_GATE_REQUIRED"], "YES")
        self.assertEqual(r["IDENTITY_GATE_EXECUTED"], "YES")
        self.assertEqual(r["SCENERY_BYPASS_APPLIED"], "NO")
        self.assertEqual(ip.validate_observability_record(r), [])

    def test_G_scenery_only_governed_novel_no_review(self):
        for novel in ("HA", "EN", "HP", "SF"):
            self.assert_bypass(self.gate(novel=novel, prompt="misty mountains at dawn",
                                         image_intent={"scene_subject": "scenery"}), "SCENERY_ONLY")

    def test_H_environment_only_no_review(self):
        self.assert_bypass(self.gate(novel="SF", prompt="empty forge hall",
                                     image_intent={"asset_role": "environment background"}), "ENVIRONMENT_ONLY")
        self.assert_bypass(self.gate(novel="EN", prompt="clouds",
                                     image_intent={"background_only": True}), "ENVIRONMENT_ONLY")

    def test_I_object_only_no_review(self):
        self.assert_bypass(self.gate(novel="HA", prompt="a jade token on a table",
                                     image_intent={"scene_subject": "object"}), "OBJECT_ONLY")

    def test_J_governed_explicitly_depicted_gate_executes(self):
        res = self.gate(novel="HP", prompt="a man at dawn", image_intent={"depicted_characters": ["liang"]})
        self.assert_governed_gate(res)
        self.assertEqual(res.decision, "REJECT_REVIEW")
        self.assertEqual(res.records[0]["CHARACTER"], "liang")
        self.assertEqual(res.records[0]["IMAGE_INTENT_SOURCE"], "STRUCTURED_DEPICTED_CHARACTER")
        self.assertEqual(res.records[0]["UPSTREAM_CHARACTER_ASSIGNED"], "YES")

    def test_K_governed_character_caller_claims_scenery_cannot_bypass(self):
        res = self.gate(novel="HP", character_id="liang", prompt="x", image_intent={"scene_subject": "scenery"})
        self.assert_governed_gate(res)
        res = self.gate(novel="HP", prompt="x",
                        image_intent={"depicted_characters": ["liang"], "scene_subject": "environment"})
        self.assert_governed_gate(res)
        # governed name in the prompt forces the governed path (documented decision)
        res = self.gate(novel="HP", prompt="Liang crosses the misty mountains",
                        image_intent={"scene_subject": "scenery"})
        self.assert_governed_gate(res)
        self.assertEqual(res.records[0]["IMAGE_INTENT_SOURCE"], "FORCED_GOVERNED_SIGNAL")
        # a Visual Director Character Identity block also forces
        res = self.gate(novel="HA", prompt="Setting: alley. Character Identity: Name: Kai; Age: 17. Camera: wide.",
                        image_intent={"scene_subject": "scenery"})
        self.assert_governed_gate(res)

    def test_L_background_only_cannot_override_structured_subject(self):
        res = self.gate(novel="SF", prompt="x", image_intent={"depicted_characters": ["jarek"], "background_only": True})
        self.assert_governed_gate(res)
        res = self.gate(novel="SF", prompt="x", image_intent={"scene_subject": "jarek", "background_only": True})
        self.assert_governed_gate(res)
        self.assertEqual(res.records[0]["IMAGE_INTENT_SOURCE"], "STRUCTURED_DEPICTED_CHARACTER")

    def test_M_truly_unknown_no_governed_character(self):
        res = self.gate(prompt="misty landscape")
        self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
        self.assertEqual(res.records[0]["IMAGE_INTENT_CLASS"], "UNDETERMINED")
        res = self.gate(novel="Azure Inkblade", character_id="bob", prompt="a stranger")
        self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
        self.assertEqual(res.records[0]["STRUCTURED_CHARACTER_VALID"], "UNVERIFIED_NO_GOVERNED_NOVEL_CONTEXT")
        self.assertTrue(res.records[0]["NO_GOVERNED_CHARACTER_REASON"])

    def test_safe_default_no_structured_intent_keeps_review(self):
        res = self.gate(novel="HP", prompt="misty mountains, no people")  # free text is not intent
        self.assert_governed_gate(res)
        self.assertEqual(res.records[0]["IMAGE_INTENT_SOURCE"], "SAFE_DEFAULT_NO_STRUCTURED_INTENT")
        # character-capable production asset role carries no scenery evidence
        res = self.gate(novel="SF", prompt="forge", image_intent={"asset_role": "tiktok scene image"})
        self.assert_governed_gate(res)

    def test_precedence_order_defined(self):
        self.assertEqual(ip.IMAGE_INTENT_PRECEDENCE[:5], (
            "STRUCTURED_DEPICTED_CHARACTER", "STRUCTURED_SCENE_SUBJECT", "STRUCTURED_ASSET_ROLE",
            "STRUCTURED_BACKGROUND_MARKER", "LEGACY_PROMPT_HEURISTIC"))
        for c in ("GOVERNED_CHARACTER_DEPICTION", "SCENERY_ONLY", "ENVIRONMENT_ONLY", "OBJECT_ONLY", "ABSTRACT",
                  "NON_CANON_SILHOUETTE"):
            self.assertIn(c, ip.IMAGE_INTENT_CLASSES)
        # scene subject beats asset role; asset role beats background marker
        res = self.gate(novel="HP", prompt="x", image_intent={"scene_subject": "object", "asset_role": "landscape"})
        self.assertEqual(res.records[0]["IMAGE_INTENT_CLASS"], "OBJECT_ONLY")
        res = self.gate(novel="HP", prompt="x", image_intent={"asset_role": "landscape", "background_only": True})
        self.assertEqual(res.records[0]["IMAGE_INTENT_CLASS"], "SCENERY_ONLY")

    def test_ambient_scope_and_prompt_registry(self):
        with ip.image_intent_scope(ip.ImageIntentRequest(scene_subject="scenery", origin="t")):
            self.assert_bypass(self.gate(novel="HP", prompt="valley"), "SCENERY_ONLY")
        p = "unique registered prompt for test %d" % id(self)
        ip.register_prompt_image_intent(p, {"scene_subject": "environment"})
        self.assert_bypass(self.gate(novel="EN", prompt=p + " Learned image feedback guidance: brighter."),
                           "ENVIRONMENT_ONLY")
        # explicit argument beats registry / ambient
        self.assert_governed_gate(self.gate(novel="EN", prompt=p, image_intent={"depicted_characters": ["kael"]}))

    def test_v2_adapter_novel_default_spec_ignored_under_scenery(self):
        from types import SimpleNamespace
        spec = SimpleNamespace(identity=SimpleNamespace(character_id="liang"), novel="hp")
        res = self.gate(spec=spec, novel="HP", prompt="misty valley", image_intent={"scene_subject": "scenery"})
        # the spec identity supplied only by the adapter is novel membership, not depiction evidence;
        # if the implementation treats it as structured, it must at least never auto-accept unverified
        if res.auto_accept_allowed:
            self.assertEqual(res.records[0]["SCENERY_BYPASS_APPLIED"], "YES")
        else:
            self.assertEqual(res.records[0]["GOVERNED_CHARACTER_DEPICTION"], "YES")


# ---------------------------------------------------------------------------
# N-Q: TikTok reuse + fallback intent preservation + prior-review integrity
# ---------------------------------------------------------------------------
class TestFallbackAndReuse(_Base):
    def fb(self, img, **kw):
        kw.setdefault("fallback_source", "tiktok_asset_group_reuse")
        kw.setdefault("asset_class", "TIKTOK_ASSET_GROUP_IMAGE")
        kw.setdefault("path_id", "FALLBACK:TEST")
        with identity_flag(True, self.log):
            return ip.evaluate_governed_fallback(img, **kw)

    def scenery_asset(self):
        p = self.img()
        res = self.gate(p, novel="HP", prompt="mountains", image_intent={"scene_subject": "scenery"},
                        write_sidecar=True)
        self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
        return p

    def test_N_tiktok_governed_reuse_requires_reverify_or_prior_review(self):
        p = self.img()
        res = self.fb(p, novel="HP", tiktok_reuse=True, image_intent={"depicted_characters": ["liang"]})
        self.assertFalse(res.auto_accept_allowed)
        r = res.records[0]
        self.assertEqual(r["TIKTOK_REUSE_USED"], "YES")
        self.assertEqual(r["TIKTOK_REUSE_IDENTITY_VERIFIED"], "NO")
        self.assertEqual(ip.validate_observability_record(r), [])
        rec = ip.build_prior_review_record(image_sha256=ip._sha256_file(p), character_id="liang", verifier_decision="PASS",
                                           human_review_status=ip.PRIOR_REVIEW_APPROVED_STATUS, reviewer="t")
        res = self.fb(p, novel="HP", tiktok_reuse=True, image_intent={"depicted_characters": ["liang"]},
                      prior_review_record=rec)
        self.assertTrue(res.auto_accept_allowed)
        self.assertEqual(res.records[0]["TIKTOK_REUSE_IDENTITY_VERIFIED"], "YES")
        # no structured intent on a TikTok reuse -> safe default governed -> blocked without review
        res = self.fb(self.img(), novel="SF", tiktok_reuse=True)
        self.assertFalse(res.auto_accept_allowed)

    def test_O_tiktok_scenery_reuse_no_unnecessary_review(self):
        p = self.scenery_asset()
        res = self.fb(p, novel="HP", tiktok_reuse=True, image_intent={"scene_subject": "scenery"})
        self.assertTrue(res.auto_accept_allowed)
        r = res.records[0]
        self.assertEqual(r["SCENERY_BYPASS_APPLIED"], "YES")
        self.assertEqual(r["TIKTOK_REUSE_IDENTITY_VERIFIED"], "NOT_REQUIRED")
        self.assertEqual(ip.validate_observability_record(r), [])

    def test_O2_scenery_slot_with_unknown_or_tampered_asset_is_governed(self):
        res = self.fb(self.img(), novel="HP", tiktok_reuse=True, image_intent={"scene_subject": "scenery"})
        self.assertFalse(res.auto_accept_allowed)
        p = self.scenery_asset()
        side = p.with_name(p.name + ".identity_preservation.json")
        d = json.loads(side.read_text(encoding="utf-8"))
        d["NOVEL"] = "tampered"
        side.write_text(json.dumps(d), encoding="utf-8")
        res = self.fb(p, novel="HP", tiktok_reuse=True, image_intent={"scene_subject": "scenery"})
        self.assertFalse(res.auto_accept_allowed)

    def test_P_fallback_preserves_governed_depiction(self):
        p = self.scenery_asset()  # even an asset recorded as scenery cannot downgrade a governed slot
        res = self.fb(p, novel="HP", asset_class="DAILY_PROMO_IMAGE", fallback_source="daily",
                      image_intent={"depicted_characters": ["liang"]})
        self.assertFalse(res.auto_accept_allowed)
        r = res.records[0]
        self.assertEqual(r["FALLBACK_ORIGINAL_INTENT_CLASS"], "GOVERNED_CHARACTER_DEPICTION")
        self.assertEqual(r["IMAGE_INTENT_CLASS"], "GOVERNED_CHARACTER_DEPICTION")
        self.assertEqual(r["FALLBACK_INTENT_PRESERVED"], "YES")
        self.assertEqual(ip.validate_observability_record(r), [])

    def test_Q_fallback_preserves_scenery_only(self):
        p = self.scenery_asset()
        res = self.fb(p, novel="SF", asset_class="DAILY_PROMO_IMAGE", fallback_source="daily",
                      image_intent={"scene_subject": "scenery"})
        self.assertTrue(res.auto_accept_allowed)
        r = res.records[0]
        self.assertEqual(r["FALLBACK_ORIGINAL_INTENT_CLASS"], "SCENERY_ONLY")
        self.assertEqual(r["IMAGE_INTENT_CLASS"], "SCENERY_ONLY")
        self.assertEqual(r["FALLBACK_INTENT_PRESERVED"], "YES")
        self.assertEqual(r["HUMAN_REVIEW_REQUIRED"], "NO")

    def test_procedural_is_non_canon_silhouette(self):
        with identity_flag(True, self.log):
            res = ip.classify_procedural_emergency_art(self.img(), path_id="T", prompt="abstract")
        self.assertEqual(res.records[0]["IMAGE_INTENT_CLASS"], "NON_CANON_SILHOUETTE")

    def test_extra_prior_review_hash_mutation_reverifies(self):
        p = self.img()
        rec = ip.build_prior_review_record(image_sha256=ip._sha256_file(p), character_id="liang", verifier_decision="PASS",
                                           human_review_status=ip.PRIOR_REVIEW_APPROVED_STATUS, reviewer="alice")
        self.assertEqual(rec["PRIOR_REVIEW_RECORD_HASH"], ip.prior_review_record_hash(rec))
        for field, value in (("REVIEWER", "mallory"), ("TIMESTAMP", "1999-01-01T00:00:00Z"),
                             ("PRIOR_REVIEW_RECORD_HASH", "0" * 64)):
            m = dict(rec)
            m[field] = value
            res = self.fb(p, novel="HP", image_intent={"depicted_characters": ["liang"]}, prior_review_record=m)
            self.assertFalse(res.auto_accept_allowed, field)
            self.assertIn("PRIOR_REVIEW_RECORD_HASH_MISMATCH_REVERIFY", res.fail_reason)
        m = dict(rec)
        m.pop("PRIOR_REVIEW_RECORD_HASH")
        res = self.fb(p, novel="HP", image_intent={"depicted_characters": ["liang"]}, prior_review_record=m)
        self.assertFalse(res.auto_accept_allowed)
        self.assertIn("PRIOR_REVIEW_RECORD_HASH_MISSING_REVERIFY", res.fail_reason)


class _StopFlow(Exception):
    pass


class TestTikTokPackReuse(_Base):
    def collab(self, files, tracks, calls):
        def gen(abbr, chapter, prompt, force_new_images=False, chapter_text="", style=""):
            calls.append(("generate", force_new_images))
            out = []
            for i in range(3):
                q = self.tmp / f"fresh{i}.png"
                q.write_bytes(FAKE + b"fresh%d" % i)
                out.append(str(q))
            return {"created": out}

        def stop(*a, **k):
            raise _StopFlow()
        return {
            "list_tiktok_assets": lambda: {"imageGroups": [{"abbr": "HP", "chapter": "3", "files": files, "tracks": tracks}],
                                           "sounds": ["s.mp3"]},
            "generate_tiktok_images": gen,
            "stable_chapter_folder": stop,
        }

    def run_pack(self, on, files):
        calls = []
        c = self.collab([str(f) for f in files], ["main-posts"] * len(files), calls)
        with identity_flag(on, self.log):
            with self.assertRaises(_StopFlow):
                pb.make_tiktok_pack("HP", "3", force_new_images=False, style="main-posts", collaborators=c)
        return calls

    def test_N_make_tiktok_pack_governed_reuse_regenerates_on(self):
        files = [self.img() for _ in range(3)]
        calls = self.run_pack(True, files)
        self.assertEqual(calls, [("generate", True)])  # unverified reuse blocked -> regenerated
        recs = self.logged()
        self.assertTrue(recs and all(r["TIKTOK_REUSE_USED"] == "YES" for r in recs))
        self.assertTrue(any(r["TIKTOK_REUSE_IDENTITY_VERIFIED"] == "NO" for r in recs))

    def test_O_make_tiktok_pack_structured_scenery_reuse_not_regenerated(self):
        files = []
        for _ in range(3):
            p = self.img()
            with identity_flag(True, self.log), ip.identity_production_context(ip.build_identity_context(abbr="HP")):
                r = ip.run_identity_acceptance_gate(p, path_id="GEN", prompt="terrace at dawn", quarantine=False,
                                                    image_intent={"scene_subject": "scenery"})
            self.assertEqual(r.records[0]["SCENERY_BYPASS_APPLIED"], "YES")
            files.append(p)
        n0 = len(self.logged())
        calls = self.run_pack(True, files)
        self.assertEqual(calls, [])  # reused without unnecessary review / regeneration
        recs = self.logged()[n0:]
        self.assertEqual(len(recs), 3)
        for r in recs:
            self.assertEqual(r["IMAGE_INTENT_SOURCE"], "REUSED_ASSET_SHA_BOUND_RECORD")
            self.assertEqual(r["TIKTOK_REUSE_IDENTITY_VERIFIED"], "NOT_REQUIRED")
            self.assertEqual(r["FALLBACK_INTENT_PRESERVED"], "YES")
            self.assertEqual(ip.validate_observability_record(r), [])

    def test_T_make_tiktok_pack_flag_off_unchanged(self):
        files = [self.img() for _ in range(3)]
        self.assertEqual(self.run_pack(False, files), [])
        self.assertFalse(self.log.exists())


# ---------------------------------------------------------------------------
# R-T: observability, logger failure, flag OFF, Visual Director
# ---------------------------------------------------------------------------
class TestObservabilityAndFlag(_Base):
    NEW = ("IMAGE_INTENT_CLASS", "IMAGE_INTENT_SOURCE", "GOVERNED_CHARACTER_DEPICTION", "UPSTREAM_CHARACTER_ASSIGNED",
           "STRUCTURED_CHARACTER_VALID", "STRUCTURED_CHARACTER_CONFLICT", "MALFORMED_CHARACTER_ID",
           "BINDING_FAILURE_REASON", "SCENERY_BYPASS_APPLIED", "SCENERY_BYPASS_REASON", "IDENTITY_GATE_REQUIRED",
           "IDENTITY_GATE_EXECUTED", "FALLBACK_ORIGINAL_INTENT_CLASS", "FALLBACK_INTENT_PRESERVED",
           "TIKTOK_REUSE_USED", "TIKTOK_REUSE_IDENTITY_VERIFIED")

    def test_R_logger_fields_complete_on_every_record_type(self):
        for f in self.NEW:
            self.assertIn(f, ip.REQUIRED_LOG_FIELDS)
        self.assertGreaterEqual(len(ip.REQUIRED_LOG_FIELDS), 56 + 15)
        cases = [dict(novel="HP", prompt="x", image_intent={"scene_subject": "scenery"}),
                 dict(novel="HP", character_id="liagn"), dict(novel="SF", character_id="jarek", prompt="x"),
                 dict(prompt="landscape"), dict(novel="SF", character_id="gray")]
        for kw in cases:
            self.gate(**kw)
        recs = self.logged()
        self.assertEqual(len(recs), len(cases))
        for r in recs:
            for f in ip.REQUIRED_LOG_FIELDS:
                self.assertIn(f, r)
            self.assertEqual(ip.validate_observability_record(r), [], r.get("IMAGE_INTENT_CLASS"))
        bad = dict(recs[0])
        bad["SCENERY_BYPASS_APPLIED"] = "YES"
        bad["GOVERNED_CHARACTER_DEPICTION"] = "YES"
        self.assertTrue(ip.validate_observability_record(bad))
        bad = dict(recs[0])
        del bad["IMAGE_INTENT_CLASS"]
        self.assertIn("IMAGE_INTENT_CLASS", ip.validate_observability_record(bad))

    def test_S_logger_failure_blocks_acceptance(self):
        def boom(*a, **k):
            raise OSError("disk full")
        for kw in (dict(novel="HP", prompt="x", image_intent={"depicted_characters": ["liang"]},
                        observations=None),
                   dict(novel="HP", prompt="x", image_intent={"scene_subject": "scenery"}),
                   dict(prompt="landscape")):
            res = self.gate(writer=boom, **kw)
            self.assertFalse(res.auto_accept_allowed, kw)
            self.assertEqual(res.decision, "FAIL_CLOSED")
            self.assertIn("OBSERVABILITY_LOG_FAILURE", res.fail_reason)
            self.assertEqual(res.records[0]["SCENERY_BYPASS_APPLIED"], "NO")

    def test_T_flag_off_restores_prior_behavior(self):
        p = self.img()
        with identity_flag(False, self.log):
            for kw in (dict(novel="EN", character_id="kaael"), dict(novel="HP", image_intent={"scene_subject": "scenery"}),
                       dict(novel="SF", character_id="scenery"), dict(novel="Eternal Nexus", character_id="jarek")):
                res = ip.run_identity_acceptance_gate(p, path_id="T", quarantine=False, **kw)
                self.assertEqual(res.decision, "BYPASS")
                self.assertTrue(res.auto_accept_allowed)
                self.assertEqual(res.records, [])
            with ip.image_intent_scope(ip.ImageIntentRequest(scene_subject="scenery")):
                res = ip.evaluate_governed_fallback(p, fallback_source="x", asset_class="TIKTOK_ASSET_GROUP_IMAGE",
                                                    path_id="T", tiktok_reuse=True)
                self.assertEqual(res.decision, "BYPASS")
        self.assertFalse(self.log.exists())
        self.assertTrue(p.exists())
        self.assertEqual(sorted(x.name for x in self.tmp.iterdir()), [p.name])


class TestVisualDirectorIntent(_Base):
    def pkg(self, on, novel, scene, **kw):
        with identity_flag(on, self.log):
            return vd.build_visual_scene_package(novel, "", scene, shots_text=[scene] * 3, **kw)

    def test_vd_named_governed_character_intent(self):
        pkg = self.pkg(True, "sf", "Jarek climbs the forge")
        self.assertEqual(pkg["image_intent"]["IMAGE_INTENT_CLASS"], "GOVERNED_CHARACTER_DEPICTION")
        self.assertEqual(pkg["image_intent"]["IMAGE_INTENT_SOURCE"], "STRUCTURED_DEPICTED_CHARACTER")
        res = self.gate(novel="SF", prompt=pkg["image_prompts"][0])
        self.assertFalse(res.auto_accept_allowed)
        self.assertEqual(res.records[0]["IMAGE_INTENT_SOURCE"], "STRUCTURED_DEPICTED_CHARACTER")
        for p in pkg["image_prompts"]:
            self.assertIn("Character Identity: Name: Jarek", p)

    def test_vd_structured_scenery_no_protagonist_injection(self):
        for novel in ("ha", "en", "hp", "sf"):
            pkg = self.pkg(True, novel, "a quiet mountain valley under mist", scene_composition={"scene_subject": "scenery"})
            self.assertEqual(pkg["image_intent"]["IMAGE_INTENT_CLASS"], "SCENERY_ONLY")
            self.assertEqual(pkg["characters"], [])
            for p in pkg["image_prompts"]:
                self.assertNotIn("Character Identity", p)
                for n in ("Kai", "Kael", "Liang", "Jarek"):
                    self.assertNotIn(n, p)
                res = self.gate(novel=novel, prompt=p)
                self.assertTrue(res.auto_accept_allowed, (novel, p))
                self.assertEqual(res.records[0]["SCENERY_BYPASS_APPLIED"], "YES")

    def test_vd_nameless_without_structured_marker_keeps_safe_default(self):
        pkg = self.pkg(True, "sf", "a quiet mountain valley under mist")
        self.assertEqual(pkg["image_intent"]["IMAGE_INTENT_SOURCE"], "SAFE_DEFAULT_NO_STRUCTURED_INTENT")
        res = self.gate(novel="SF", prompt=pkg["image_prompts"][0])
        self.assertFalse(res.auto_accept_allowed)

    def test_vd_named_character_beats_scenery_marker(self):
        pkg = self.pkg(True, "hp", "Liang enters the ruined sect hall", scene_composition={"scene_subject": "scenery"})
        self.assertEqual(pkg["image_intent"]["IMAGE_INTENT_CLASS"], "GOVERNED_CHARACTER_DEPICTION")
        res = self.gate(novel="HP", prompt=pkg["image_prompts"][0])
        self.assertFalse(res.auto_accept_allowed)

    def test_vd_flag_off_unchanged(self):
        with identity_flag(False, self.log):
            a = vd.build_visual_scene_package("hp", "", "Liang enters the ruined sect hall",
                                              shots_text=["Liang enters the ruined sect hall"] * 3)
            b = vd.build_visual_scene_package("hp", "", "Liang enters the ruined sect hall",
                                              shots_text=["Liang enters the ruined sect hall"] * 3,
                                              scene_composition={"scene_subject": "scenery"})
        self.assertEqual(a, b)
        self.assertNotIn("image_intent", a)


# ---------------------------------------------------------------------------
# Part H: production path wiring through app.py (all providers mocked, GPU_GENERATIONS=0)
# ---------------------------------------------------------------------------
import app  # noqa: E402
from tests import test_identity_production_paths as tip  # noqa: E402  (module only; no test classes re-exported)


class TestAppIntentWiring(tip._V2Base):
    def test_v2_structured_scenery_bypasses_and_governed_blocks(self):
        with identity_flag(True, self.log):
            src = app.generate_promo_image_v2(self.style, "misty mountain valley at dawn, empty terrace", self.target,
                                              abbr="HP", index=1, materialize=self.materialize, novel="Hundredfold Path",
                                              chapter="1", scene_text="misty mountain valley at dawn, empty terrace",
                                              promo_master_enabled=False,
                                              image_intent={"scene_subject": "scenery", "origin": "test.v2"})
        self.assertEqual(src, "v2:main_posts")
        rec = self.log_records()[-1]
        self.assertEqual(rec["IMAGE_INTENT_CLASS"], "SCENERY_ONLY")
        self.assertEqual(rec["SCENERY_BYPASS_APPLIED"], "YES")
        self.assertEqual(ip.validate_observability_record(rec), [])
        # a governed name in scene_text forces the governed path even with a scenery claim
        with identity_flag(True, self.log):
            with self.assertRaises(app.V2ImageGenerationError):
                app.generate_promo_image_v2(self.style, "mountain valley at dawn", self.target, abbr="HP", index=2,
                                            materialize=self.materialize, novel="Hundredfold Path", chapter="1",
                                            scene_text="Liang crosses the mountain valley at dawn",
                                            promo_master_enabled=False, image_intent={"scene_subject": "scenery"})
        self.assertEqual(self.log_records()[-1]["GOVERNED_CHARACTER_DEPICTION"], "YES")

    def test_v2_no_structured_intent_keeps_legacy_on_behaviour(self):
        with identity_flag(True, self.log):
            with self.assertRaises(app.V2ImageGenerationError):
                app.generate_promo_image_v2(self.style, "misty mountain valley at dawn", self.target, abbr="HP", index=3,
                                            materialize=self.materialize, novel="Hundredfold Path", chapter="1",
                                            scene_text="misty mountain valley at dawn", promo_master_enabled=False)
        self.assertEqual(self.log_records()[-1]["IMAGE_INTENT_SOURCE"], "SAFE_DEFAULT_NO_STRUCTURED_INTENT")

    def test_v2_flag_off_ignores_intent(self):
        with identity_flag(False, self.log):
            src = app.generate_promo_image_v2(self.style, "misty valley", self.target, abbr="HP", index=4,
                                              materialize=self.materialize, novel="Hundredfold Path", chapter="1",
                                              scene_text="misty valley", promo_master_enabled=False,
                                              image_intent={"depicted_characters": ["liang"]})
        self.assertEqual(src, "v2:main_posts")
        self.assertFalse(self.log.exists())


class TestAppStaticWiring(_Base):
    def test_v1_primitives_and_v2_accept_image_intent(self):
        import inspect
        for fn in (app.create_local_stable_diffusion_image, app.create_openai_image, app.create_google_ai_image,
                   app.generate_promo_image_v2, app._v1_identity_acceptance_gate, app._identity_fallback_allowed):
            self.assertIn("image_intent", inspect.signature(fn).parameters, fn.__name__)

    def test_every_decorated_production_path_has_an_asset_role(self):
        src = Path(app.__file__).read_text(encoding="utf-8").splitlines()
        decorated = []
        for i, line in enumerate(src):
            if line.startswith("@_identity_context_from_args("):
                j = i + 1
                while not src[j].startswith("def "):
                    j += 1
                decorated.append(src[j].split("def ", 1)[1].split("(", 1)[0])
        self.assertGreaterEqual(len(decorated), 20)
        for name in decorated:
            self.assertIn(name, app._IDENTITY_PATH_ASSET_ROLES, name)
            role = app._IDENTITY_PATH_ASSET_ROLES[name]
            self.assertIn(role, ip.CHARACTER_CAPABLE_ASSET_ROLES, name)
            self.assertNotIn(ip._vocab_key(role), ip.ASSET_ROLE_CLASSES)  # no scenery evidence by role alone

    def test_v1_gate_uses_explicit_intent(self):
        p = self.img()
        with identity_flag(True, self.log):
            app._v1_identity_acceptance_gate(p, "V1:test", "misty valley",
                                             identity_context=ip.build_identity_context(abbr="SF"),
                                             image_intent={"scene_subject": "scenery"})
            with self.assertRaises(Exception) as cm:
                app._v1_identity_acceptance_gate(self.img(), "V1:test", "misty valley",
                                                 identity_context=ip.build_identity_context(abbr="SF"))
        self.assertTrue(ip.is_identity_block(cm.exception))

    def test_app_tiktok_fallback_flagged(self):
        p = self.img()
        # production TikTok call sites run inside @_identity_context_from_args (structured abbr)
        with identity_flag(True, self.log), ip.identity_production_context(ip.build_identity_context(abbr="SF")):
            ok = app._identity_fallback_allowed(p, asset_class="CHAPTER_PACK_IMAGE", fallback_source="t",
                                                path_id="FALLBACK:test", tiktok_reuse=True)
        self.assertFalse(ok)
        rec = self.logged()[-1]
        self.assertEqual(rec["TIKTOK_REUSE_USED"], "YES")
        self.assertEqual(rec["TIKTOK_REUSE_IDENTITY_VERIFIED"], "NO")

    def test_vd_via_app_registers_intent(self):
        saved = {k: os.environ.get(k) for k in ("VISUAL_DIRECTOR_ENABLED",)}
        os.environ["VISUAL_DIRECTOR_ENABLED"] = "1"
        try:
            with identity_flag(True, self.log):
                prompts = app.make_chapter_image_prompts(
                    "Soul Forge Era", "Jarek dragged iron chains through the forge undercity.",
                    ["Jarek dragged iron chains.", "Jarek looked up.", "Jarek ran."], novel="sf")
                hits = [ip.lookup_prompt_image_intent(p) for p in prompts]
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertTrue(any(h is not None and "Jarek" in h.depicted_characters for h in hits), hits)


if __name__ == "__main__":
    unittest.main()
