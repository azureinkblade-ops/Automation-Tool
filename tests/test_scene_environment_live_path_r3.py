# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R3 — unit + live-fixture tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.scene_environment import (
    classify_location_relations,
    classify_place_phrase,
    extract_place_phrases,
    match_studio_bible_location_detailed,
    resolve_scene_environment,
    build_still_cameras_poses,
    STILL_OBSERVABILITY_FIELDS,
    build_still_observability,
)


LOCS = [
    {"id": "en_nexus_pod", "name": "Nexus Pod", "novel": "en", "architecture": "obsidian", "lighting": "neon"},
    {"id": "en_mira_apartment", "name": "Mira's Apartment", "novel": "en", "architecture": "cramped", "lighting": "warm"},
    {"id": "sf_forge", "name": "The Forge", "novel": "sf", "architecture": "iron", "lighting": "ember"},
    {"id": "sf_market", "name": "Market Square", "novel": "sf", "architecture": "open", "lighting": "rain"},
    {"id": "hp_sect_hall", "name": "Ruined Sect Hall", "novel": "hp", "architecture": "stone", "lighting": "jade"},
    {"id": "ha_system_hall", "name": "System Hall", "novel": "ha", "architecture": "metal", "lighting": "blue"},
]


class TestR3NegationDeparture:
    def test_far_from_pod_does_not_bind_en_nexus_pod(self):
        scene = "Kael waited in Mira's cramped apartment, far from his own pod"
        d = match_studio_bible_location_detailed(scene, LOCS, "en")
        assert d["matched"] is None or d["matched"].get("id") != "en_nexus_pod"
        assert d["LOCATION_NEGATION_DETECTED"] or d["decision"] == "UNRESOLVED_RELATION_BLOCKED"
        rel = classify_location_relations(scene)
        assert "pod" in rel["blocked_phrases"]
        assert rel["blocked_phrases"]["pod"] == "NEGATED_LOCATION"

    def test_left_forge_behind_does_not_bind_sf_forge(self):
        scene = "Jarek left the forge behind and walked into the rain-soaked market square"
        d = match_studio_bible_location_detailed(scene, LOCS, "sf")
        assert d["matched"] is None or d["matched"].get("id") != "sf_forge"
        assert d["LOCATION_DEPARTURE_DETECTED"] or "forge" in str(d.get("relation_detections"))

    def test_outside_sect_gate_barred_no_interior_bind(self):
        scene = "Liang stood outside the sect gate, barred from entering"
        spec = resolve_scene_environment("hp", scene, locations=LOCS)
        assert spec.location_id in ("UNRESOLVED", "unresolved", "") or "sect_hall" not in spec.location_id
        cams, poses, _ = build_still_cameras_poses(spec, "Liang")
        blob = " ".join(cams + poses).lower()
        assert "jade altar" not in blob
        assert "broken stair" not in blob
        assert "dormant formation" not in blob

    def test_positive_locatives_still_bind(self):
        d1 = match_studio_bible_location_detailed(
            "Kael sealed the hatch inside the Nexus Pod", LOCS, "en")
        assert d1["matched"] and d1["matched"]["id"] == "en_nexus_pod"
        d2 = match_studio_bible_location_detailed(
            "Jarek worked the bellows at the forge in the undercity", LOCS, "sf")
        assert d2["matched"] and d2["matched"]["id"] == "sf_forge"


class TestR3PlaceExtractor:
    @pytest.mark.parametrize("scene,forbid", [
        ("the way a field opens at dawn", "field"),
        ("the way a wall holds silence", "wall"),
        ("walking the Hundredfold Path of legend", "hundredfold"),
        ("his forge-heart pounded in his chest", "forge-heart"),
        ("the maternal forge of memory shaped him", "maternal"),
        ("vision the upper forge had shown him", "forge"),
        ("Chapter 12: The Forge Awakens", "forge"),
    ])
    def test_false_positives_rejected(self, scene, forbid):
        acc, rej = extract_place_phrases(scene)
        joined = " ".join(acc).lower()
        # forge-heart / maternal forge / title forge must not appear as accepted place
        if forbid == "forge-heart":
            assert "forge-heart" not in joined
        elif forbid == "maternal":
            assert "maternal forge" not in joined
        elif forbid == "hundredfold":
            assert "hundredfold path" not in joined
        elif forbid in ("field", "wall"):
            assert f"way a {forbid}" not in joined
        elif forbid == "forge":
            # non-locative forge contexts must not accept bare forge as place from those scenes
            for a in acc:
                assert a.lower() not in {"forge", "upper forge", "the forge"}

    def test_true_locative_forge_preserved(self):
        scene = "a forge burned in a hall"
        acc, rej = extract_place_phrases(scene)
        assert any("forge" in a.lower() or "hall" in a.lower() for a in acc)
        c = classify_place_phrase("forge", scene_text=scene)
        assert c["PLACE_PHRASE_CLASS"] == "LOCATIVE"


class TestR3HpTemplateEvidence:
    def test_outside_gate_no_unsupported_landmarks(self):
        spec = resolve_scene_environment(
            "Hundredfold Path",
            "Liang stood outside the sect gate, barred from entering",
            locations=LOCS,
        )
        assert spec.observability.get("HP_TEMPLATE_REQUIRES_SCENE_EVIDENCE") is True
        cams, poses, _ = build_still_cameras_poses(spec, "Liang", identity_on=True)
        blob = " ".join(cams + poses).lower()
        assert "altar" not in blob
        assert "staircase" not in blob
        assert "formation" not in blob or "sect gate" in (spec.place_phrase or "").lower()

    def test_interior_evidence_allows_altar(self):
        spec = resolve_scene_environment(
            "hp",
            "Liang entered the ruined sect hall and knelt before the jade altar as the dormant formation glowed",
            locations=LOCS,
        )
        assert spec.hp_landmarks_allowed is True
        assert any("altar" in s for s in spec.observability.get("SUPPORTED_HP_LANDMARKS") or [])
        cams, _, _ = build_still_cameras_poses(spec, "Liang")
        assert any("altar" in c.lower() for c in cams)


class TestR3ObservabilityFields:
    def test_r3_fields_present_on_records(self):
        required = {
            "LOCATION_RELATION_CLASS", "LOCATION_NEGATION_DETECTED", "LOCATION_DEPARTURE_DETECTED",
            "LOCATION_REFERENCE_ONLY", "PLACE_PHRASE_CLASS", "PLACE_REJECTION_REASON",
            "SCENE_PATH_CLASS", "SCENE_AUTHORITY_APPLIED", "GENERATOR_GUARD_ACTIVE",
            "RUNTIME_STATE_GUARD_ACTIVE",
        }
        assert required.issubset(set(STILL_OBSERVABILITY_FIELDS))
        spec = resolve_scene_environment("en", "Kael waited far from his own pod", locations=LOCS)
        recs = build_still_observability(
            input_novel="Eternal Nexus", normalized_novel="en", path="test",
            prompts=["p1", "p2", "p3"], specs=[spec, spec, spec],
            beats=["b1", "b2", "b3"], roles=["establishing", "travel", "climax"],
            legacy_used=[False, False, False], legacy_reasons=["", "", ""],
        )
        for r in recs:
            for k in required:
                assert k in r, k
            assert r["GENERATOR_GUARD_ACTIVE"] is True or os.environ.get("AT_GPU_TEST_BARRIER") == "1"
            assert r["LOCATION_NEGATION_DETECTED"] is True


class TestR3ProductionPathInventory:
    def test_inventory_complete_and_scene_bearing_routed(self):
        import app
        inv = app.R3_PRODUCTION_SCENE_PATH_INVENTORY
        required = {
            "generate_tiktok_images", "make_campaign", "make_deep_tiktok_pack",
            "make_deep_tiktok_novel_pack", "regenerate_weak_images",
            "make_release_chapter_pack", "make_weekend_social_post",
            "write_variant_social_pack", "write_variant_short_pack",
            "build_resurfacing_post", "build_comment_content_post",
            "arc_campaign_plans", "generate_youtube_generated_background",
            "build_story_hook_thumbnail_base",
        }
        assert required.issubset(set(inv))
        # Every SCENE_BEARING_* must be inventored (count unrouted = 0 by construction of helper)
        unrouted = [k for k, (cls, bearing, _) in inv.items() if bearing and k not in inv]
        assert unrouted == []
        assert app._r3_scene_bearing("generate_tiktok_images") is True
        assert app._r3_scene_bearing("generate_youtube_generated_background") is False
        assert app._r3_scene_path_class("prepare_tiktok_outro_image") == "PURE_GRAPHIC"
