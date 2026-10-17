# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_PREACCESS_STATE_R13 tests."""
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
    {"id": "ha_alley", "name": "Alley", "novel": "ha", "architecture": "narrow", "lighting": "dim"},
]


def mid(s, n):
    return (match_studio_bible_location_detailed(s, LOCS, n).get("matched") or {}).get("id")


class TestR13Request:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael was requesting access into the Nexus Pod", "en", "en_nexus_pod"),
        ("Kael asked admission to Mira's apartment", "en", "en_mira_apartment"),
        ("Jarek was seeking permission to enter the forge", "sf", "sf_forge"),
        ("Kai was petitioning for entry to the System Hall", "ha", "ha_system_hall"),
        ("Liang was waiting for clearance into the ruined sect hall", "hp", "hp_sect_hall"),
    ])
    def test_request_no_bind(self, s, n, f):
        assert mid(s, n) != f
        rel = classify_location_relations(s)
        roles = [m.get("LOCATION_ROLE") for m in rel["LOCATION_RELATION_MENTIONS"]]
        assert all(r != "SUCCESSFUL_DESTINATION" or not m.get("BIND_ALLOWED")
                   for m, r in zip(rel["LOCATION_RELATION_MENTIONS"], roles))
        assert any(m.get("ACCESS_PHASE") in ("REQUEST", "WAIT") for m in rel["LOCATION_RELATION_MENTIONS"])


class TestR13Test:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael was testing passage into the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was checking the entrance to the forge", "sf", "sf_forge"),
        ("Kai was probing the way into the System Hall", "ha", "ha_system_hall"),
        ("Liang was examining access to the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael was trying the gate to Mira's apartment", "en", "en_mira_apartment"),
        ("Jarek was testing whether the forge could be entered", "sf", "sf_forge"),
    ])
    def test_test_no_bind(self, s, n, f):
        assert mid(s, n) != f
        rel = classify_location_relations(s)
        assert any(m.get("ACCESS_PHASE") in ("TEST", "INSPECTION") for m in rel["LOCATION_RELATION_MENTIONS"])


class TestR13Approach:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael was approaching the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was standing at the entrance to the forge", "sf", "sf_forge"),
        ("Kai was reaching the gate of the System Hall", "ha", "ha_system_hall"),
        ("Liang was waiting outside the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael was coming up to the threshold of Mira's apartment", "en", "en_mira_apartment"),
    ])
    def test_approach_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR13GrantedPreserved:
    @pytest.mark.parametrize("s,n,w", [
        ("Kael crossed into Mira's apartment", "en", "en_mira_apartment"),
        ("Jarek passed inside the forge", "sf", "sf_forge"),
        ("Kai was escorted into the System Hall", "ha", "ha_system_hall"),
        ("Liang was admitted into the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael made it through into Mira's apartment", "en", "en_mira_apartment"),
    ])
    def test_granted(self, s, n, w):
        assert mid(s, n) == w


class TestR13DeniedPreserved:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael was turned away at the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was blocked at the forge", "sf", "sf_forge"),
        ("Kai was turned away at the System Hall", "ha", "ha_system_hall"),
        ("Liang could not get past the ruined sect hall", "hp", "hp_sect_hall"),
    ])
    def test_denied(self, s, n, f):
        assert mid(s, n) != f


class TestR13CurrentPreserved:
    def test_inside_binds(self):
        s = "Kael sat inside Mira's apartment"
        assert mid(s, "en") == "en_mira_apartment"


class TestR13MultiValid:
    def test_request_plus_current(self):
        s = "Kael was requesting access into the Nexus Pod, but he sat inside Mira's apartment"
        assert mid(s, "en") == "en_mira_apartment"
        assert mid(s, "en") != "en_nexus_pod"

    def test_test_plus_current(self):
        s = "Jarek was testing passage into the forge, but he waited inside the market square"
        assert mid(s, "sf") == "sf_market"


class TestR13Obs:
    def test_phase_fields(self):
        r = classify_location_relations("Kael was requesting access into the Nexus Pod")
        assert r.get("R13_PREACCESS_OBSERVABILITY_COMPLETE") is True
        m = r["LOCATION_RELATION_MENTIONS"][0]
        for k in (
            "ACCESS_PHASE", "ACCESS_RESULT", "ACCESS_REQUESTED", "ACCESS_TESTED",
            "ACCESS_INSPECTED", "ACCESS_APPROACHED", "ACCESS_TRAVERSAL_COMPLETE",
            "LOCATION_ROLE", "FINAL_BIND_ALLOWED", "FINAL_BIND_REASON",
        ):
            assert k in m
        assert m.get("BIND_ALLOWED") is False
        assert m.get("LOCATION_ROLE") not in {"CURRENT_SITE", "SUCCESSFUL_DESTINATION"}
