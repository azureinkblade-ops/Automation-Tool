# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_LOCATION_RELATION_PARAPHRASE_REMEDIATION_R5 unit tests."""
from __future__ import annotations

import pytest

from tools.scene_environment import (
    LOCATION_RELATION_CURRENT,
    LOCATION_RELATION_NEGATED,
    LOCATION_RELATION_REFERENCE,
    STILL_OBSERVABILITY_FIELDS,
    build_still_observability,
    classify_location_relations,
    match_studio_bible_location_detailed,
    resolve_scene_environment,
)

LOCS = [
    {"id": "en_nexus_pod", "name": "Nexus Pod", "novel": "en", "architecture": "obsidian", "lighting": "neon"},
    {"id": "en_mira_apartment", "name": "Mira's Apartment", "novel": "en", "architecture": "cramped", "lighting": "warm"},
    {"id": "sf_forge", "name": "The Forge", "novel": "sf", "architecture": "iron", "lighting": "ember"},
    {"id": "sf_market", "name": "Market Square", "novel": "sf", "architecture": "open", "lighting": "rain"},
    {"id": "hp_sect_hall", "name": "Ruined Sect Hall", "novel": "hp", "architecture": "stone", "lighting": "jade"},
    {"id": "ha_system_hall", "name": "System Hall", "novel": "ha", "architecture": "metal", "lighting": "blue"},
]

R5_OBS = {
    "RAW_LOCATION_MENTION", "LOCATION_RELATION_CLASS", "RELATION_FAMILY",
    "MATCHED_CUE", "MATCHED_CUE_FAMILY", "CLAUSE_OR_WINDOW", "NEGATION_SCOPE",
    "REFERENCE_SCOPE", "CURRENT_LOCATION_EVIDENCE", "BIND_ALLOWED", "REJECTION_REASON",
}


def _classes(scene):
    rel = classify_location_relations(scene)
    return [(m["NORMALIZED"], m["RELATION_CLASS"]) for m in rel["LOCATION_RELATION_MENTIONS"]]


def _bound(scene, nov):
    d = match_studio_bible_location_detailed(scene, LOCS, nov)
    return (d.get("matched") or {}).get("id"), d.get("decision")


class TestR5ReferenceFamilies:
    @pytest.mark.parametrize("scene,nov,forbid", [
        ("Kael told them about the Nexus Pod.", "en", "en_nexus_pod"),
        ("Kai told him about the System Hall", "ha", "ha_system_hall"),
        ("Liang told her about the ruined sect hall", "hp", "hp_sect_hall"),
        ("He kept thinking back to the Nexus Pod", "en", "en_nexus_pod"),
        ("She mentioned the Nexus Pod in passing", "en", "en_nexus_pod"),
        ("Jarek described the forge he had once seen", "sf", "sf_forge"),
        ("They heard about the System Hall", "ha", "ha_system_hall"),
        ("Kael could still remember the Nexus Pod", "en", "en_nexus_pod"),
        ("She dreamed about the ruined sect hall", "hp", "hp_sect_hall"),
        ("He read about the market square", "sf", "sf_market"),
        ("The story about the forge was only a memory", "sf", "sf_forge"),
        ("he remembered the story of the Nexus Pod from childhood", "en", "en_nexus_pod"),
    ])
    def test_reference_does_not_bind(self, scene, nov, forbid):
        rel = classify_location_relations(scene)
        assert any(m["RELATION_CLASS"] == LOCATION_RELATION_REFERENCE for m in rel["LOCATION_RELATION_MENTIONS"])
        mid, _ = _bound(scene, nov)
        assert mid != forbid


class TestR5NegationFamilies:
    @pytest.mark.parametrize("scene,nov,forbid", [
        ("Kai never entered the system hall that night", "ha", "ha_system_hall"),
        ("Kael did not go into the Nexus Pod", "en", "en_nexus_pod"),
        ("Kael didn't enter the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek never went into the forge", "sf", "sf_forge"),
        ("Liang did not enter the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael wasn't in the Nexus Pod", "en", "en_nexus_pod"),
        ("Kai was not inside the system hall", "ha", "ha_system_hall"),
        ("Jarek hadn't reached the forge", "sf", "sf_forge"),
        ("Kael had not returned to the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek never arrived at the forge", "sf", "sf_forge"),
        ("Jarek was not anywhere near the forge", "sf", "sf_forge"),
        ("Kael remained a long way from the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek avoided the forge entirely and waited in the market square", "sf", "sf_forge"),
        ("Jarek was nowhere near the forge; he stood in the market square", "sf", "sf_forge"),
    ])
    def test_negated_does_not_bind(self, scene, nov, forbid):
        rel = classify_location_relations(scene)
        assert any(m["RELATION_CLASS"] == LOCATION_RELATION_NEGATED for m in rel["LOCATION_RELATION_MENTIONS"])
        mid, _ = _bound(scene, nov)
        assert mid != forbid


class TestR5Scope:
    def test_negation_scope_forge_vs_market(self):
        scene = "Jarek never entered the forge and instead waited in the market square."
        rel = classify_location_relations(scene)
        by = {m["NORMALIZED"]: m["RELATION_CLASS"] for m in rel["LOCATION_RELATION_MENTIONS"]}
        assert any("forge" in k and v == LOCATION_RELATION_NEGATED for k, v in by.items())
        assert any("market" in k and v == LOCATION_RELATION_CURRENT for k, v in by.items())
        mid, _ = _bound(scene, "sf")
        assert mid == "sf_market"

    def test_reference_scope_pod_vs_apartment(self):
        scene = "Kael told Mira about the Nexus Pod while sitting in Mira's apartment."
        rel = classify_location_relations(scene)
        by = {m["NORMALIZED"]: m["RELATION_CLASS"] for m in rel["LOCATION_RELATION_MENTIONS"]}
        assert any("pod" in k and v == LOCATION_RELATION_REFERENCE for k, v in by.items())
        assert any("apartment" in k and v == LOCATION_RELATION_CURRENT for k, v in by.items())
        mid, _ = _bound(scene, "en")
        assert mid == "en_mira_apartment"
        assert mid != "en_nexus_pod"


class TestR5PositiveControls:
    @pytest.mark.parametrize("scene,nov,want", [
        ("Kael entered the Nexus Pod.", "en", "en_nexus_pod"),
        ("Kael went into the Nexus Pod.", "en", "en_nexus_pod"),
        ("Kael returned to the Nexus Pod.", "en", "en_nexus_pod"),
        ("Kael arrived at the Nexus Pod.", "en", "en_nexus_pod"),
        ("Jarek entered the forge.", "sf", "sf_forge"),
        ("Jarek worked inside the forge.", "sf", "sf_forge"),
        ("Jarek reached the forge.", "sf", "sf_forge"),
        ("Told them inside the Nexus Pod.", "en", "en_nexus_pod"),
        ("Thinking back while inside the forge.", "sf", "sf_forge"),
        ("Kai stood inside the system hall", "ha", "ha_system_hall"),
        ("Liang waited within the ruined sect hall", "hp", "hp_sect_hall"),
    ])
    def test_clear_current_still_binds(self, scene, nov, want):
        rel = classify_location_relations(scene)
        assert any(m["RELATION_CLASS"] == LOCATION_RELATION_CURRENT for m in rel["LOCATION_RELATION_MENTIONS"])
        mid, _ = _bound(scene, nov)
        assert mid == want


class TestR5Observability:
    def test_mention_fields(self):
        rel = classify_location_relations("Kael told them about the Nexus Pod while sitting in Mira's apartment")
        assert rel["PER_MENTION_LOCATION_RELATION"] is True
        assert rel["PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE"] is True
        assert rel["LOCATION_RELATION_MENTIONS"]
        for m in rel["LOCATION_RELATION_MENTIONS"]:
            assert R5_OBS.issubset(m.keys())

    def test_still_obs_flag(self):
        assert "PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE" in STILL_OBSERVABILITY_FIELDS
        spec = resolve_scene_environment(
            "en", "Kael told them about the Nexus Pod while sitting in Mira's apartment", locations=LOCS
        )
        recs = build_still_observability(
            input_novel="Eternal Nexus", normalized_novel="en", path="test",
            prompts=["p1", "p2", "p3"], specs=[spec, spec, spec],
            beats=["b1", "b2", "b3"], roles=["establishing", "travel", "climax"],
            legacy_used=[False, False, False], legacy_reasons=["", "", ""],
        )
        for r in recs:
            assert r.get("PARAPHRASE_RELATION_OBSERVABILITY_COMPLETE") is True
            assert r.get("PER_MENTION_LOCATION_RELATION") is True
