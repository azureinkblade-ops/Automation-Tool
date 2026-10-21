# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_INTENT_ATTEMPT_COMPLEMENT_GENERALIZATION_R8 tests."""
from __future__ import annotations

import pytest
from tools.scene_environment import classify_location_relations, match_studio_bible_location_detailed

LOCS = [
    {"id": "en_nexus_pod", "name": "Nexus Pod", "novel": "en", "architecture": "obsidian", "lighting": "neon"},
    {"id": "en_mira_apartment", "name": "Mira's Apartment", "novel": "en", "architecture": "cramped", "lighting": "warm"},
    {"id": "sf_forge", "name": "The Forge", "novel": "sf", "architecture": "iron", "lighting": "ember"},
    {"id": "sf_market", "name": "Market Square", "novel": "sf", "architecture": "open", "lighting": "rain"},
    {"id": "hp_sect_hall", "name": "Ruined Sect Hall", "novel": "hp", "architecture": "stone", "lighting": "jade"},
    {"id": "ha_system_hall", "name": "System Hall", "novel": "ha", "architecture": "metal", "lighting": "blue"},
]


def mid(s, n):
    return (match_studio_bible_location_detailed(s, LOCS, n).get("matched") or {}).get("id")


class TestR8Intent:
    @pytest.mark.parametrize("s,n,f", [
        ("wished to enter the forge", "sf", "sf_forge"),
        ("resolved to return to the forge", "sf", "sf_forge"),
        ("decided to visit the forge", "sf", "sf_forge"),
        ("chose to head toward the forge", "sf", "sf_forge"),
        ("elected to stop at the forge", "sf", "sf_forge"),
        ("proposed to enter the forge", "sf", "sf_forge"),
        ("arranged to visit the forge", "sf", "sf_forge"),
        ("contemplated entering the forge", "sf", "sf_forge"),
        ("considered returning to the forge", "sf", "sf_forge"),
    ])
    def test_intent_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR8Attempt:
    @pytest.mark.parametrize("s", [
        "tried to enter the forge",
        "struggled to reach the forge",
        "made an effort to enter the forge",
        "failed to reach the forge",
    ])
    def test_attempt_no_bind(self, s):
        assert mid(s, "sf") != "sf_forge"

    def test_managed_enters(self):
        assert mid("managed to enter the forge", "sf") == "sf_forge"


class TestR8Occupancy:
    @pytest.mark.parametrize("s,n,w", [
        ("occupied the forge", "sf", "sf_forge"),
        ("lingered in the forge", "sf", "sf_forge"),
        ("resided in Mira's apartment", "en", "en_mira_apartment"),
        ("sheltered inside the ruined sect hall", "hp", "hp_sect_hall"),
        ("rested in the System Hall", "ha", "ha_system_hall"),
    ])
    def test_occupy(self, s, n, w):
        assert mid(s, n) == w


class TestR8Contrast:
    def test_occupy_vs_plan(self):
        assert mid("occupied the forge", "sf") == "sf_forge"
        assert mid("planned to occupy the forge", "sf") != "sf_forge"

    def test_linger_vs_intend(self):
        assert mid("lingered in the ruined sect hall", "hp") == "hp_sect_hall"
        assert mid("intended to linger in the ruined sect hall", "hp") != "hp_sect_hall"


class TestR8Scope:
    def test_wish_but_linger(self):
        s = "Kael wished to enter the Nexus Pod but lingered in Mira's apartment."
        assert mid(s, "en") == "en_mira_apartment"
        assert mid(s, "en") != "en_nexus_pod"


class TestR8Obs:
    def test_flag(self):
        rel = classify_location_relations("wished to enter the forge")
        assert rel.get("R8_PREDICATE_OBSERVABILITY_COMPLETE") is True
