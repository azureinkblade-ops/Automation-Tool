# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_LOCATION_RELATION_SCOPE_AND_INTENT_R7 unit tests."""
from __future__ import annotations

import pytest

from tools.scene_environment import (
    LOCATION_RELATION_CURRENT,
    LOCATION_RELATION_DEPARTED,
    LOCATION_RELATION_NEGATED,
    LOCATION_RELATION_REFERENCE,
    classify_location_relations,
    match_studio_bible_location_detailed,
)

LOCS = [
    {"id": "en_nexus_pod", "name": "Nexus Pod", "novel": "en", "architecture": "obsidian", "lighting": "neon"},
    {"id": "en_mira_apartment", "name": "Mira's Apartment", "novel": "en", "architecture": "cramped", "lighting": "warm"},
    {"id": "sf_forge", "name": "The Forge", "novel": "sf", "architecture": "iron", "lighting": "ember"},
    {"id": "sf_market", "name": "Market Square", "novel": "sf", "architecture": "open", "lighting": "rain"},
    {"id": "hp_sect_hall", "name": "Ruined Sect Hall", "novel": "hp", "architecture": "stone", "lighting": "jade"},
    {"id": "ha_system_hall", "name": "System Hall", "novel": "ha", "architecture": "metal", "lighting": "blue"},
]


def _mid(scene, nov):
    return (match_studio_bible_location_detailed(scene, LOCS, nov).get("matched") or {}).get("id")


class TestR7Intent:
    @pytest.mark.parametrize("scene,nov,forbid", [
        ("Kael meant to enter the Nexus Pod.", "en", "en_nexus_pod"),
        ("Jarek planned to stop at the forge.", "sf", "sf_forge"),
        ("Kai was preparing to enter the System Hall.", "ha", "ha_system_hall"),
        ("Liang hoped to return to the ruined sect hall.", "hp", "hp_sect_hall"),
        ("Kael intended to reach the Nexus Pod.", "en", "en_nexus_pod"),
        ("Jarek was on the way to the forge.", "sf", "sf_forge"),
    ])
    def test_intent_no_bind(self, scene, nov, forbid):
        assert _mid(scene, nov) != forbid
        rel = classify_location_relations(scene)
        assert rel.get("R7_SCOPE_OBSERVABILITY_COMPLETE") is True


class TestR7Attempt:
    @pytest.mark.parametrize("scene,nov,forbid", [
        ("Kael tried to enter the Nexus Pod.", "en", "en_nexus_pod"),
        ("Jarek attempted to reach the forge.", "sf", "sf_forge"),
        ("Kai was trying to reach the System Hall.", "ha", "ha_system_hall"),
        ("Liang tried unsuccessfully to enter the ruined sect hall.", "hp", "hp_sect_hall"),
    ])
    def test_attempt_no_bind(self, scene, nov, forbid):
        assert _mid(scene, nov) != forbid


class TestR7CompletionContrast:
    def test_planned_vs_entered(self):
        assert _mid("planned to enter the forge", "sf") != "sf_forge"
        assert _mid("entered the forge", "sf") == "sf_forge"

    def test_going_to_work_vs_worked(self):
        assert _mid("was going to work in the forge", "sf") != "sf_forge"
        assert _mid("worked in the forge", "sf") == "sf_forge"

    def test_intended_vs_returned(self):
        assert _mid("intended to return to the Nexus Pod", "en") != "en_nexus_pod"
        assert _mid("returned to the Nexus Pod", "en") == "en_nexus_pod"


class TestR7Coordination:
    def test_plan_but_wait(self):
        scene = "Kael planned to enter the Nexus Pod but waited in Mira's apartment."
        rel = classify_location_relations(scene)
        pairs = [(m["NORMALIZED"], m["RELATION_CLASS"]) for m in rel["LOCATION_RELATION_MENTIONS"]]
        assert any("pod" in k and v != LOCATION_RELATION_CURRENT for k, v in pairs)
        assert any("apartment" in k and v == LOCATION_RELATION_CURRENT for k, v in pairs)
        assert _mid(scene, "en") == "en_mira_apartment"

    def test_left_and_waited(self):
        scene = "Jarek had left the forge and waited in the market square."
        assert _mid(scene, "sf") == "sf_market"
        assert _mid(scene, "sf") != "sf_forge"

    def test_avoided_but_worked(self):
        scene = "Jarek avoided the forge but worked in the market square."
        rel = classify_location_relations(scene)
        assert any(m["RELATION_CLASS"] == LOCATION_RELATION_NEGATED for m in rel["LOCATION_RELATION_MENTIONS"])
        assert _mid(scene, "sf") == "sf_market"

    def test_remembered_and_stayed(self):
        scene = "Liang remembered the ruined sect hall and stayed in a rented room."
        assert _mid(scene, "hp") != "hp_sect_hall"
        rel = classify_location_relations(scene)
        assert any(m["RELATION_CLASS"] == LOCATION_RELATION_REFERENCE for m in rel["LOCATION_RELATION_MENTIONS"])


class TestR7SameClauseDest:
    def test_planned_visit_both(self):
        scene = "Kael planned to visit the Nexus Pod and Mira's apartment."
        assert _mid(scene, "en") not in ("en_nexus_pod", "en_mira_apartment")

    def test_left_for(self):
        scene = "Kael left the Nexus Pod for Mira's apartment."
        rel = classify_location_relations(scene)
        assert any("pod" in m["NORMALIZED"] and m["RELATION_CLASS"] == LOCATION_RELATION_DEPARTED
                   for m in rel["LOCATION_RELATION_MENTIONS"])
        assert _mid(scene, "en") != "en_nexus_pod"


class TestR7Observability:
    def test_r7_fields(self):
        rel = classify_location_relations("Kael meant to enter the Nexus Pod but sat in Mira's apartment")
        keys = {"CLAUSE_ID", "PREDICATE_HEAD", "PREDICATE_FAMILY", "INTENT_DETECTED", "DESTINATION_ONLY", "BIND_ALLOWED"}
        assert rel["LOCATION_RELATION_MENTIONS"]
        for m in rel["LOCATION_RELATION_MENTIONS"]:
            assert keys.issubset(m.keys())
