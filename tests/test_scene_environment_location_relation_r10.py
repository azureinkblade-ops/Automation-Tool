# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_CONSTRUCTION_NORMALIZATION_R10 tests."""
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


class TestR10Nominalized:
    @pytest.mark.parametrize("s,n,f", [
        ("Walking into the Nexus Pod stayed Kael's selected course", "en", "en_nexus_pod"),
        ("Entering the forge remained the preferred option", "sf", "sf_forge"),
        ("Returning to the System Hall was still the chosen path", "ha", "ha_system_hall"),
        ("Visiting the ruined sect hall remained the stated objective", "hp", "hp_sect_hall"),
        ("Going back to the Nexus Pod was the intended course", "en", "en_nexus_pod"),
        ("Walking into the forge remained the selected course", "sf", "sf_forge"),
    ])
    def test_nominalized_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR10PlanNoun:
    @pytest.mark.parametrize("s,n,f", [
        ("The Nexus Pod remained the selected destination", "en", "en_nexus_pod"),
        ("Entry into the forge was the chosen objective", "sf", "sf_forge"),
        ("The route into the System Hall was only the proposed course", "ha", "ha_system_hall"),
    ])
    def test_plan_noun_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR10FailedAccess:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael found no way into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was refused passage into the forge", "sf", "sf_forge"),
        ("Kai was denied passage to the System Hall", "ha", "ha_system_hall"),
        ("Liang could find no entrance to the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael was prevented from reaching the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was blocked from entering the forge", "sf", "sf_forge"),
        ("Kai was turned away from the System Hall", "ha", "ha_system_hall"),
        ("Jarek never got through to the forge", "sf", "sf_forge"),
    ])
    def test_failed_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR10Denial:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael had no way into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek had no access to the forge", "sf", "sf_forge"),
        ("Kai was denied entry to the System Hall", "ha", "ha_system_hall"),
        ("Liang was refused passage to the ruined sect hall", "hp", "hp_sect_hall"),
        ("Jarek was barred from the forge", "sf", "sf_forge"),
        ("Kael was kept out of Mira's apartment", "en", "en_mira_apartment"),
        ("Kai was locked out of the System Hall", "ha", "ha_system_hall"),
        ("Jarek was turned away from the forge", "sf", "sf_forge"),
    ])
    def test_denial_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR10Modal:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael ought to walk into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was to enter the forge", "sf", "sf_forge"),
        ("Were Kai to walk into the System Hall the night would change", "ha", "ha_system_hall"),
        ("Kael would have gone into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek could have walked into the forge", "sf", "sf_forge"),
        ("Liang might have stepped inside the ruined sect hall", "hp", "hp_sect_hall"),
    ])
    def test_modal_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR10Success:
    @pytest.mark.parametrize("s,n,w", [
        ("Kael got through into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was admitted into the forge", "sf", "sf_forge"),
        ("Kai was allowed inside the System Hall", "ha", "ha_system_hall"),
        ("Liang gained access to the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael crossed into Mira's apartment", "en", "en_mira_apartment"),
        ("Jarek broke through into the forge", "sf", "sf_forge"),
        ("Kai reached the interior of the System Hall", "ha", "ha_system_hall"),
        ("Liang entered the ruined sect hall successfully", "hp", "hp_sect_hall"),
        ("Kael got through to the interior of the Nexus Pod", "en", "en_nexus_pod"),
    ])
    def test_success_binds(self, s, n, w):
        assert mid(s, n) == w


class TestR10Contrast:
    def test_fail_vs_success(self):
        assert mid("found no way into the forge", "sf") != "sf_forge"
        assert mid("got through into the forge", "sf") == "sf_forge"
        assert mid("was refused passage into the System Hall", "ha") != "ha_system_hall"
        assert mid("was admitted into the System Hall", "ha") == "ha_system_hall"
        assert mid("was blocked from reaching the Nexus Pod", "en") != "en_nexus_pod"
        assert mid("reached the Nexus Pod", "en") == "en_nexus_pod"

    def test_nominalized_vs_actual(self):
        assert mid("Entering the forge remained the plan", "sf") != "sf_forge"
        assert mid("Entered the forge", "sf") == "sf_forge"
        assert mid("Returning to the ruined sect hall was the chosen course", "hp") != "hp_sect_hall"
        assert mid("Returned to the ruined sect hall", "hp") == "hp_sect_hall"


class TestR10Multi:
    def test_nominalized_but_inside(self):
        s = "Entering the Nexus Pod remained Kael's chosen course, but he was inside Mira's apartment."
        assert mid(s, "en") == "en_mira_apartment"
        assert mid(s, "en") != "en_nexus_pod"

    def test_failed_and_waited(self):
        s = "Jarek found no way into the forge and waited in the market square."
        assert mid(s, "sf") == "sf_market"
        assert mid(s, "sf") != "sf_forge"


class TestR10Obs:
    def test_flag(self):
        r = classify_location_relations("Walking into the forge stayed Jarek's selected course")
        assert r.get("R10_CONSTRUCTION_OBSERVABILITY_COMPLETE") is True
        m = r["LOCATION_RELATION_MENTIONS"][0]
        for k in ("ACTION_FORM", "ACTION_NOMINALIZED", "PLAN_NOUN", "PLAN_RELATION",
                  "ACCESS_STATE", "ACCESS_DENIED", "ACCESS_GRANTED", "MODAL_AUXILIARY",
                  "RESULT_POLARITY", "RELATION_CLASS", "BIND_ALLOWED", "REJECTION_REASON"):
            assert k in m
