# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_PREACCESS_EVENT_OPERATOR_R14 tests."""
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


class TestR14AuthPending:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael was awaiting authorization for the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was submitting for admission to the forge", "sf", "sf_forge"),
        ("Kai had pending clearance to the System Hall", "ha", "ha_system_hall"),
        ("Liang was under review for entry to the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael was seeking approval to enter Mira's apartment", "en", "en_mira_apartment"),
        ("Application for access to the forge remained pending", "sf", "sf_forge"),
    ])
    def test_auth_pending_no_bind(self, s, n, f):
        assert mid(s, n) != f
        rel = classify_location_relations(s)
        assert any(m.get("PREACCESS_OPERATOR") == "AUTHORIZATION_PENDING" for m in rel["LOCATION_RELATION_MENTIONS"])
        assert all(not m.get("BIND_ALLOWED") for m in rel["LOCATION_RELATION_MENTIONS"]
                   if "pod" in m.get("NORMALIZED", "") or "forge" in m.get("NORMALIZED", "")
                   or "hall" in m.get("NORMALIZED", "") or "apartment" in m.get("NORMALIZED", ""))


class TestR14Query:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael was verifying entry to the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek was evaluating access to the forge", "sf", "sf_forge"),
        ("Kai was assessing whether the System Hall could be entered", "ha", "ha_system_hall"),
        ("Liang was determining whether the route into the ruined sect hall was usable", "hp", "hp_sect_hall"),
        ("Kael was checking whether passage remained open to Mira's apartment", "en", "en_mira_apartment"),
    ])
    def test_query_no_bind(self, s, n, f):
        assert mid(s, n) != f
        rel = classify_location_relations(s)
        assert any(m.get("PREACCESS_OPERATOR") in ("ACCESS_QUERY", "ACCESS_INSPECTION")
                   for m in rel["LOCATION_RELATION_MENTIONS"])


class TestR14Boundary:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael neared the entrance to the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek came alongside the gate of the forge", "sf", "sf_forge"),
        ("Kai drew up before the System Hall", "ha", "ha_system_hall"),
        ("Liang moved toward the threshold of the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael closed on the boundary of Mira's apartment", "en", "en_mira_apartment"),
        ("Jarek arrived outside the forge", "sf", "sf_forge"),
    ])
    def test_boundary_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR14Inchoative:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael started toward the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek began moving toward the forge", "sf", "sf_forge"),
        ("Kai set off in the direction of the System Hall", "ha", "ha_system_hall"),
        ("Liang started making for the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael began the approach to Mira's apartment", "en", "en_mira_apartment"),
    ])
    def test_inchoative_no_bind(self, s, n, f):
        assert mid(s, n) != f
        rel = classify_location_relations(s)
        assert any(m.get("PREACCESS_OPERATOR") == "MOTION_INCHOATIVE" for m in rel["LOCATION_RELATION_MENTIONS"])


class TestR14Attempt:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael tried to enter the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek attempted passage into the forge", "sf", "sf_forge"),
        ("Kai worked toward reaching the System Hall", "ha", "ha_system_hall"),
    ])
    def test_attempt_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR14CompletionOverride:
    def test_admitted_after_request(self):
        s = "Kael requested admission and was admitted into Mira's apartment"
        assert mid(s, "en") == "en_mira_apartment"

    def test_passed_inside_after_test(self):
        s = "Jarek tested the gate, then passed inside the forge"
        assert mid(s, "sf") == "sf_forge"


class TestR14FailureOverride:
    def test_refused_after_request(self):
        s = "Kael requested entry but was turned away at the Nexus Pod"
        assert mid(s, "en") != "en_nexus_pod"

    def test_blocked_after_test(self):
        s = "Jarek tested passage and found it blocked at the forge"
        assert mid(s, "sf") != "sf_forge"


class TestR14Current:
    def test_inside(self):
        assert mid("Kael sat inside Mira's apartment", "en") == "en_mira_apartment"


class TestR14Multi:
    def test_auth_plus_current(self):
        s = "Kael was awaiting authorization for the Nexus Pod, but he sat inside Mira's apartment"
        assert mid(s, "en") == "en_mira_apartment"

    def test_inchoative_plus_current(self):
        s = "Jarek started toward the forge, but he waited inside the market square"
        assert mid(s, "sf") == "sf_market"


class TestR14Obs:
    def test_fields(self):
        r = classify_location_relations("Kael was awaiting authorization for the Nexus Pod")
        assert r.get("R14_PREACCESS_OPERATOR_OBSERVABILITY_COMPLETE") is True
        m = r["LOCATION_RELATION_MENTIONS"][0]
        for k in (
            "PREACCESS_OPERATOR", "EVENT_REALIZATION", "AUTHORIZATION_PENDING",
            "ACCESS_QUERY", "ACCESS_INSPECTION", "BOUNDARY_APPROACH", "MOTION_INCHOATIVE",
            "ACCESS_PHASE", "ACCESS_RESULT", "EXPLICIT_COMPLETION_EVIDENCE",
            "EXPLICIT_FAILURE_EVIDENCE", "LOCATION_ROLE", "FINAL_BIND_ALLOWED", "FINAL_BIND_REASON",
        ):
            assert k in m
        assert m.get("BIND_ALLOWED") is False
        assert m.get("LOCATION_ROLE") not in {"CURRENT_SITE", "SUCCESSFUL_DESTINATION"}
