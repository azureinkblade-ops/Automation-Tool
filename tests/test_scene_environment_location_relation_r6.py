# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_LOCATION_RELATION_GENERALIZATION_R6 unit tests."""
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


def _has(scene, cls):
    rel = classify_location_relations(scene)
    return any(m["RELATION_CLASS"] == cls for m in rel["LOCATION_RELATION_MENTIONS"])


class TestR6CompositionFlags:
    def test_flags(self):
        rel = classify_location_relations("Kael failed to reach the Nexus Pod")
        assert rel["RELATION_CLASSIFICATION_COMPOSITIONAL"] is True
        assert rel["LEXICAL_FAMILY_NORMALIZATION"] is True
        assert rel["R6_RELATION_OBSERVABILITY_COMPLETE"] is True
        m = rel["LOCATION_RELATION_MENTIONS"][0]
        for k in ("RELATION_HEAD", "NEGATION", "ASPECT", "PREPOSITION", "LEXICAL_FAMILY", "CLAUSE_SPAN"):
            assert k in m


class TestR6NegationComposition:
    @pytest.mark.parametrize("scene", [
        "failed to reach the forge",
        "never set foot inside the forge",
        "wasn't anywhere near the forge",
        "didn't make it to the forge",
        "had yet to reach the forge",
        "kept well clear of the forge",
    ])
    def test_neg_no_bind(self, scene):
        assert _has(scene, LOCATION_RELATION_NEGATED)
        assert _mid(scene, "sf") != "sf_forge"


class TestR6Departure:
    @pytest.mark.parametrize("scene", [
        "had already left the forge",
        "walked away from the forge",
        "made his way out of the forge",
        "exited the forge",
        "headed away from the forge",
        "put the forge behind him",
    ])
    def test_dep_no_bind(self, scene):
        rel = classify_location_relations(scene)
        classes = {m["RELATION_CLASS"] for m in rel["LOCATION_RELATION_MENTIONS"]}
        assert LOCATION_RELATION_DEPARTED in classes or LOCATION_RELATION_NEGATED in classes
        assert _mid(scene, "sf") != "sf_forge"


class TestR6Reference:
    @pytest.mark.parametrize("scene,nov,forbid", [
        ("a remembered tale of the Nexus Pod", "en", "en_nexus_pod"),
        ("she had heard stories about the forge", "sf", "sf_forge"),
        ("he pictured the System Hall", "ha", "ha_system_hall"),
        ("the memory of the alley returned", "ha", "ha_system_hall"),
        ("they discussed the Nexus Pod", "en", "en_nexus_pod"),
    ])
    def test_ref_no_bind(self, scene, nov, forbid):
        assert _has(scene, LOCATION_RELATION_REFERENCE)
        assert _mid(scene, nov) != forbid


class TestR6Current:
    @pytest.mark.parametrize("scene,nov,want", [
        ("worked in the forge", "sf", "sf_forge"),
        ("stood in the forge", "sf", "sf_forge"),
        ("waited at the forge", "sf", "sf_forge"),
        ("sat inside the Nexus Pod", "en", "en_nexus_pod"),
        ("remained within the ruined sect hall", "hp", "hp_sect_hall"),
        ("returned to the System Hall", "ha", "ha_system_hall"),
    ])
    def test_current_binds(self, scene, nov, want):
        assert _has(scene, LOCATION_RELATION_CURRENT)
        assert _mid(scene, nov) == want


class TestR6Intent:
    @pytest.mark.parametrize("scene", [
        "was going to enter the forge",
        "tried to reach the forge",
        "was about to enter the forge",
        "planned to visit the forge",
        "headed toward the forge",
    ])
    def test_intent_no_bind(self, scene):
        assert _mid(scene, "sf") != "sf_forge"


class TestR6Scope:
    def test_remember_plus_work(self):
        scene = "He remembered the Nexus Pod while working in Mira's apartment."
        rel = classify_location_relations(scene)
        pairs = {m["NORMALIZED"]: m["RELATION_CLASS"] for m in rel["LOCATION_RELATION_MENTIONS"]}
        assert any("pod" in k and v == LOCATION_RELATION_REFERENCE for k, v in pairs.items())
        assert any("apartment" in k and v == LOCATION_RELATION_CURRENT for k, v in pairs.items())
        assert _mid(scene, "en") == "en_mira_apartment"

    def test_left_plus_wait(self):
        scene = "Jarek had already left the forge and was waiting in the market square."
        rel = classify_location_relations(scene)
        pairs = {m["NORMALIZED"]: m["RELATION_CLASS"] for m in rel["LOCATION_RELATION_MENTIONS"]}
        assert any("forge" in k and v == LOCATION_RELATION_DEPARTED for k, v in pairs.items())
        assert any("market" in k and v == LOCATION_RELATION_CURRENT for k, v in pairs.items())
        assert _mid(scene, "sf") == "sf_market"
