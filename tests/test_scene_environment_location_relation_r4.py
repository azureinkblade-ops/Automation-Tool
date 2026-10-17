# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_LOCATION_RELATION_REMEDIATION_R4 unit tests."""
from __future__ import annotations

import pytest

from tools.scene_environment import (
    LOCATION_RELATION_CURRENT,
    LOCATION_RELATION_NEGATED,
    LOCATION_RELATION_DEPARTED,
    LOCATION_RELATION_REFERENCE,
    LOCATION_RELATION_PRECEDENCE,
    classify_location_relations,
    match_studio_bible_location_detailed,
    resolve_scene_environment,
    build_still_observability,
    STILL_OBSERVABILITY_FIELDS,
)

LOCS = [
    {"id": "en_nexus_pod", "name": "Nexus Pod", "novel": "en", "architecture": "obsidian", "lighting": "neon"},
    {"id": "en_mira_apartment", "name": "Mira's Apartment", "novel": "en", "architecture": "cramped", "lighting": "warm"},
    {"id": "sf_forge", "name": "The Forge", "novel": "sf", "architecture": "iron", "lighting": "ember"},
    {"id": "sf_market", "name": "Market Square", "novel": "sf", "architecture": "open", "lighting": "rain"},
    {"id": "hp_sect_hall", "name": "Ruined Sect Hall", "novel": "hp", "architecture": "stone", "lighting": "jade"},
    {"id": "ha_system_hall", "name": "System Hall", "novel": "ha", "architecture": "metal", "lighting": "blue"},
]


class TestR4ReferenceOnly:
    @pytest.mark.parametrize("scene", [
        "he remembered the story of the Nexus Pod from childhood",
        "Kael recalled the tale of the Nexus Pod",
        "she heard news of the Nexus Pod",
        "they learned the legend of the Nexus Pod",
        "he spoke of the Nexus Pod",
        "she dreamed of the Nexus Pod",
        "a memory of the Nexus Pod haunted him",
        "vision the upper forge had shown him faded",
    ])
    def test_reference_only_does_not_bind(self, scene):
        nov = "sf" if "forge" in scene.lower() else "en"
        forbid = "sf_forge" if nov == "sf" else "en_nexus_pod"
        rel = classify_location_relations(scene)
        assert any(m["RELATION_CLASS"] == LOCATION_RELATION_REFERENCE for m in rel["LOCATION_RELATION_MENTIONS"])
        d = match_studio_bible_location_detailed(scene, LOCS, nov)
        mid = (d.get("matched") or {}).get("id")
        assert mid != forbid
        assert mid is None or d["decision"] != "BOUND_POSITIVE_PLACE_EVIDENCE" or mid != forbid


class TestR4ProximityNegation:
    @pytest.mark.parametrize("scene,nov,forbid", [
        ("Jarek was nowhere near the forge; he stood in the market square", "sf", "sf_forge"),
        ("Jarek was not near the forge", "sf", "sf_forge"),
        ("Kael waited far from his own pod", "en", "en_nexus_pod"),
        ("Kael was far away from his pod", "en", "en_nexus_pod"),
        ("Kai was not inside the system hall", "ha", "ha_system_hall"),
        ("Liang was not within the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kai was not at the system hall", "ha", "ha_system_hall"),
        ("Kael was not in the Nexus Pod", "en", "en_nexus_pod"),
    ])
    def test_negated_does_not_bind(self, scene, nov, forbid):
        rel = classify_location_relations(scene)
        assert any(m["RELATION_CLASS"] == LOCATION_RELATION_NEGATED for m in rel["LOCATION_RELATION_MENTIONS"])
        d = match_studio_bible_location_detailed(scene, LOCS, nov)
        mid = (d.get("matched") or {}).get("id")
        assert mid != forbid


class TestR4PositiveControls:
    def test_inside_pod_binds(self):
        d = match_studio_bible_location_detailed("Kael waited inside the Nexus Pod", LOCS, "en")
        assert d["matched"] and d["matched"]["id"] == "en_nexus_pod"

    def test_stood_near_forge_binds(self):
        d = match_studio_bible_location_detailed("Jarek stood near the forge", LOCS, "sf")
        assert d["matched"] and d["matched"]["id"] == "sf_forge"

    def test_multi_clause_remembered_plus_current(self):
        scene = "Kael remembered the Nexus Pod while waiting in Mira's apartment"
        rel = classify_location_relations(scene)
        classes = {m["NORMALIZED"]: m["RELATION_CLASS"] for m in rel["LOCATION_RELATION_MENTIONS"]}
        assert any("pod" in k and v == LOCATION_RELATION_REFERENCE for k, v in classes.items())
        assert any("apartment" in k and v == LOCATION_RELATION_CURRENT for k, v in classes.items())
        d = match_studio_bible_location_detailed(scene, LOCS, "en")
        assert d["matched"] and d["matched"]["id"] == "en_mira_apartment"
        assert d["matched"]["id"] != "en_nexus_pod"


class TestR4PerMentionAndPrecedence:
    def test_per_mention_not_sentence_wide(self):
        scene = "Kael remembered the Nexus Pod while waiting in Mira's apartment"
        rel = classify_location_relations(scene)
        assert rel["PER_MENTION_LOCATION_RELATION"] is True
        # primary stays CURRENT when a current mention coexists
        assert rel["LOCATION_RELATION_CLASS"] == LOCATION_RELATION_CURRENT
        # reference flag may be True (a mention is reference) but must not block apartment
        assert rel["LOCATION_REFERENCE_ONLY"] is True
        assert "nexus pod" in rel["blocked_phrases"]
        assert not any("apartment" in b for b in rel["blocked_phrases"])

    def test_precedence_defined(self):
        assert LOCATION_RELATION_PRECEDENCE[LOCATION_RELATION_NEGATED] > LOCATION_RELATION_PRECEDENCE[LOCATION_RELATION_DEPARTED]
        assert LOCATION_RELATION_PRECEDENCE[LOCATION_RELATION_DEPARTED] > LOCATION_RELATION_PRECEDENCE[LOCATION_RELATION_REFERENCE]
        assert LOCATION_RELATION_PRECEDENCE[LOCATION_RELATION_REFERENCE] > LOCATION_RELATION_PRECEDENCE[LOCATION_RELATION_CURRENT]
        rel = classify_location_relations("nowhere near the forge")
        assert rel["LOCATION_RELATION_PRECEDENCE_DEFINED"] is True

    def test_negated_beats_reference_on_same_phrase(self):
        # synthetic: if both fire, NEGATED wins in blocked_phrases
        scene = "he remembered the forge but was nowhere near the forge"
        rel = classify_location_relations(scene)
        assert rel["blocked_phrases"].get("forge") == LOCATION_RELATION_NEGATED


class TestR4Observability:
    def test_mention_fields_complete(self):
        required = {"RAW", "NORMALIZED", "RELATION_CLASS", "triggers", "CURRENT_EVIDENCE", "BIND_ALLOWED", "REJECTION_REASON"}
        rel = classify_location_relations(
            "Kael remembered the Nexus Pod while waiting in Mira's apartment"
        )
        assert rel["LOCATION_RELATION_MENTIONS"]
        for m in rel["LOCATION_RELATION_MENTIONS"]:
            assert required.issubset(m.keys())

    def test_still_obs_includes_r4_fields(self):
        assert "LOCATION_RELATION_MENTIONS" in STILL_OBSERVABILITY_FIELDS
        assert "PER_MENTION_LOCATION_RELATION" in STILL_OBSERVABILITY_FIELDS
        spec = resolve_scene_environment("en", "Kael remembered the Nexus Pod while waiting in Mira's apartment", locations=LOCS)
        recs = build_still_observability(
            input_novel="Eternal Nexus", normalized_novel="en", path="test",
            prompts=["p1", "p2", "p3"], specs=[spec, spec, spec],
            beats=["b1", "b2", "b3"], roles=["establishing", "travel", "climax"],
            legacy_used=[False, False, False], legacy_reasons=["", "", ""],
        )
        for r in recs:
            assert "LOCATION_RELATION_MENTIONS" in r
            assert r.get("PER_MENTION_LOCATION_RELATION") is True
            assert r.get("LOCATION_RELATION_PRECEDENCE_DEFINED") is True


class TestR4HomeBiasNegatives:
    @pytest.mark.parametrize("nov,scene,forbid", [
        ("en", "Kael remembered the story of the Nexus Pod from childhood", "en_nexus_pod"),
        ("en", "something shifted in the air around Kael", "en_nexus_pod"),
        ("sf", "Jarek was nowhere near the forge; he stood in the market square", "sf_forge"),
        ("sf", "Jarek thought of home while crossing the slag courtyard", "sf_forge"),
        ("hp", "Liang sat at a scribe desk copying ledgers in a rented room", "hp_sect_hall"),
        ("hp", "Liang remembered the ruined sect hall of legend", "hp_sect_hall"),
        ("ha", "Kai walked far from the alley into the open plaza", "ha_system_hall"),
        ("ha", "Kai recalled the tale of the System Hall", "ha_system_hall"),
    ])
    def test_no_home_bias_bind(self, nov, scene, forbid):
        d = match_studio_bible_location_detailed(scene, LOCS, nov)
        mid = (d.get("matched") or {}).get("id")
        assert mid != forbid
