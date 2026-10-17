# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_MODAL_RESULT_CONSTRUCTION_GENERALIZATION_R9 tests."""
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


class TestR9Modal:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael would enter the Nexus Pod", "en", "en_nexus_pod"),
        ("Kael would go into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek might enter the forge", "sf", "sf_forge"),
        ("Jarek might go into the forge", "sf", "sf_forge"),
        ("Kai could enter the System Hall later", "ha", "ha_system_hall"),
        ("Liang may visit the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael was likely to enter the Nexus Pod", "en", "en_nexus_pod"),
        ("Kai was expected to enter the System Hall later", "ha", "ha_system_hall"),
    ])
    def test_modal_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR9Conditional:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael would enter the Nexus Pod if conditions allowed", "en", "en_nexus_pod"),
        ("Jarek might reach the forge before nightfall", "sf", "sf_forge"),
        ("Liang could return to the ruined sect hall tomorrow", "hp", "hp_sect_hall"),
        ("Kai would stop at the System Hall later", "ha", "ha_system_hall"),
    ])
    def test_conditional_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR9Inverted:
    @pytest.mark.parametrize("s,n,f", [
        ("To enter the Nexus Pod was his choice", "en", "en_nexus_pod"),
        ("Entering the forge remained the plan", "sf", "sf_forge"),
        ("A visit to the System Hall was still only an objective", "ha", "ha_system_hall"),
        ("Reaching the ruined sect hall was what she intended", "hp", "hp_sect_hall"),
        ("Going into the Nexus Pod was on the agenda", "en", "en_nexus_pod"),
    ])
    def test_inverted_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR9Schedule:
    @pytest.mark.parametrize("s,n,f", [
        ("The Nexus Pod was on tomorrow's itinerary", "en", "en_nexus_pod"),
        ("The forge was next week's stop", "sf", "sf_forge"),
        ("The System Hall appeared on the schedule", "ha", "ha_system_hall"),
        ("The ruined sect hall was booked for later", "hp", "hp_sect_hall"),
        ("The Nexus Pod remained a future objective", "en", "en_nexus_pod"),
        ("The forge was the next destination", "sf", "sf_forge"),
    ])
    def test_schedule_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR9Failed:
    @pytest.mark.parametrize("s,n,f", [
        ("Jarek came up short of the forge", "sf", "sf_forge"),
        ("Kai was foiled at the System Hall", "ha", "ha_system_hall"),
        ("Kael fell short of the Nexus Pod", "en", "en_nexus_pod"),
        ("Liang never made the ruined sect hall", "hp", "hp_sect_hall"),
        ("Jarek couldn't make the forge", "sf", "sf_forge"),
        ("Kael was stopped before the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was turned back before the forge", "sf", "sf_forge"),
    ])
    def test_failed_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR9Success:
    @pytest.mark.parametrize("s,n,w", [
        ("Kael made it into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek got inside the forge", "sf", "sf_forge"),
        ("Kai got through into the System Hall", "ha", "ha_system_hall"),
        ("Liang successfully entered the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael ended up inside Mira's apartment", "en", "en_mira_apartment"),
    ])
    def test_success_binds(self, s, n, w):
        assert mid(s, n) == w


class TestR9Occupancy:
    @pytest.mark.parametrize("s,n,w", [
        ("Kai was stationed in the System Hall", "ha", "ha_system_hall"),
        ("Jarek was posted in the forge", "sf", "sf_forge"),
        ("Kael was based in Mira's apartment", "en", "en_mira_apartment"),
        ("Liang remained on site at the ruined sect hall", "hp", "hp_sect_hall"),
        ("Jarek spent the night in the market square", "sf", "sf_market"),
        ("Kael was present inside Mira's apartment", "en", "en_mira_apartment"),
        ("Kai kept watch from inside the System Hall", "ha", "ha_system_hall"),
    ])
    def test_occupy(self, s, n, w):
        assert mid(s, n) == w


class TestR9Contrast:
    def test_modal_vs_actual(self):
        assert mid("would enter the forge", "sf") != "sf_forge"
        assert mid("entered the forge", "sf") == "sf_forge"
        assert mid("might stay in Mira's apartment", "en") != "en_mira_apartment"
        assert mid("stayed in Mira's apartment", "en") == "en_mira_apartment"
        assert mid("could return to the System Hall", "ha") != "ha_system_hall"
        assert mid("returned to the System Hall", "ha") == "ha_system_hall"
        assert mid("was expected to reach the ruined sect hall", "hp") != "hp_sect_hall"
        assert mid("reached the ruined sect hall", "hp") == "hp_sect_hall"

    def test_result_contrast(self):
        assert mid("came up short of the forge", "sf") != "sf_forge"
        assert mid("made it into the forge", "sf") == "sf_forge"
        assert mid("was foiled before the System Hall", "ha") != "ha_system_hall"
        assert mid("got inside the System Hall", "ha") == "ha_system_hall"
        assert mid("failed to make the Nexus Pod", "en") != "en_nexus_pod"
        assert mid("finally reached the Nexus Pod", "en") == "en_nexus_pod"


class TestR9Multi:
    def test_modal_but_stationed(self):
        s = "Kael might enter the Nexus Pod later but was stationed in Mira's apartment."
        assert mid(s, "en") == "en_mira_apartment"
        assert mid(s, "en") != "en_nexus_pod"

    def test_failed_and_night(self):
        s = "Jarek came up short of the forge and spent the night in the market square."
        assert mid(s, "sf") == "sf_market"
        assert mid(s, "sf") != "sf_forge"


class TestR9Obs:
    def test_flag(self):
        r = classify_location_relations("would enter the forge")
        assert r.get("R9_CONSTRUCTION_OBSERVABILITY_COMPLETE") is True
        assert r.get("R8_PREDICATE_OBSERVABILITY_COMPLETE") is True
        m = r["LOCATION_RELATION_MENTIONS"][0]
        assert "MODAL_CLASS" in m
        assert "RESULT_POLARITY" in m
        assert "INVERTED_INTENT" in m
        assert "BIND_ALLOWED" in m
