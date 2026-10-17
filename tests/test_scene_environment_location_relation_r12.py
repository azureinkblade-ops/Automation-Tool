# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_AUTHORITATIVE_EVENT_ROLE_R12 tests."""
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
BIND_ROLES = {"CURRENT_SITE", "SUCCESSFUL_DESTINATION"}


def mid(s, n):
    return (match_studio_bible_location_detailed(s, LOCS, n).get("matched") or {}).get("id")


class TestR12RoleAuthority:
    def test_bind_only_from_role(self):
        rel = classify_location_relations("Kael sat inside Mira's apartment")
        for m in rel["LOCATION_RELATION_MENTIONS"]:
            if m.get("BIND_ALLOWED"):
                assert m.get("LOCATION_ROLE") in BIND_ROLES
            if m.get("LOCATION_ROLE") not in BIND_ROLES:
                assert m.get("BIND_ALLOWED") is False
                assert m.get("FINAL_BIND_ALLOWED") is False

    def test_planned_not_bind(self):
        s = "Entering the Nexus Pod served as Kael's assignment"
        assert mid(s, "en") != "en_nexus_pod"
        rel = classify_location_relations(s)
        for m in rel["LOCATION_RELATION_MENTIONS"]:
            if "pod" in m.get("NORMALIZED", ""):
                assert m.get("LOCATION_ROLE") == "PLANNED_SITE"
                assert m.get("BIND_ALLOWED") is False


class TestR12Classificatory:
    @pytest.mark.parametrize("s,n,f", [
        ("Entering the forge served as the assignment", "sf", "sf_forge"),
        ("Entry into the Nexus Pod amounted to their target", "en", "en_nexus_pod"),
        ("Going into the System Hall qualified as the next objective", "ha", "ha_system_hall"),
        ("Arrival at the ruined sect hall registered as the mission goal", "hp", "hp_sect_hall"),
        ("Securing a foothold in the forge served as the edict", "sf", "sf_forge"),
        ("A drive into the Nexus Pod qualified as the compact", "en", "en_nexus_pod"),
        ("A bid into the System Hall registered as the warrant", "ha", "ha_system_hall"),
        ("Taking a path into the ruined sect hall functioned as the mandate", "hp", "hp_sect_hall"),
    ])
    def test_classificatory_no_bind(self, s, n, f):
        assert mid(s, n) != f


class TestR12Denied:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael was sent back from the Nexus Pod", "en", "en_nexus_pod"),
        ("The crossing into the forge was closed", "sf", "sf_forge"),
        ("Passage to the System Hall was unavailable", "ha", "ha_system_hall"),
        ("They were turned away before the ruined sect hall", "hp", "hp_sect_hall"),
        ("Jarek was waved off at the lip of the forge", "sf", "sf_forge"),
        ("Kael found the crossing closed at the Nexus Pod", "en", "en_nexus_pod"),
        ("Kai couldn't force a path into the System Hall", "ha", "ha_system_hall"),
    ])
    def test_denied(self, s, n, f):
        assert mid(s, n) != f


class TestR12Granted:
    @pytest.mark.parametrize("s,n,w", [
        ("Kael was waved through into Mira's apartment", "en", "en_mira_apartment"),
        ("Jarek was shown inside the forge", "sf", "sf_forge"),
        ("Kai was escorted through into the System Hall", "ha", "ha_system_hall"),
        ("Liang was admitted beyond the entrance into the ruined sect hall", "hp", "hp_sect_hall"),
        ("Jarek was guided across the threshold into the forge", "sf", "sf_forge"),
        ("Kael was brought inside Mira's apartment", "en", "en_mira_apartment"),
    ])
    def test_granted(self, s, n, w):
        assert mid(s, n) == w


class TestR12Unknown:
    @pytest.mark.parametrize("s,n,f", [
        ("Kael approached the gate to the Nexus Pod", "en", "en_nexus_pod"),
        ("Jarek asked for entry to the forge", "sf", "sf_forge"),
        ("Kai waited for permission to enter the System Hall", "ha", "ha_system_hall"),
        ("Liang tried the entrance to the ruined sect hall", "hp", "hp_sect_hall"),
        ("Kael reached the threshold of the Nexus Pod", "en", "en_nexus_pod"),
    ])
    def test_unknown_no_success(self, s, n, f):
        assert mid(s, n) != f


class TestR12Current:
    def test_inside_binds_current_site(self):
        s = "Kael remained inside Mira's apartment"
        assert mid(s, "en") == "en_mira_apartment"
        rel = classify_location_relations(s)
        roles = [m.get("LOCATION_ROLE") for m in rel["LOCATION_RELATION_MENTIONS"] if m.get("BIND_ALLOWED")]
        assert "CURRENT_SITE" in roles or "SUCCESSFUL_DESTINATION" in roles


class TestR12Multi:
    def test_served_while_inside(self):
        s = "Entering the Nexus Pod served as Kael's assignment, while he remained inside Mira's apartment."
        assert mid(s, "en") == "en_mira_apartment"
        assert mid(s, "en") != "en_nexus_pod"

    def test_sent_back_but_shown(self):
        s = "Jarek was sent back from the forge but was shown inside the market square."
        assert mid(s, "sf") == "sf_market"
        assert mid(s, "sf") != "sf_forge"


class TestR12Obs:
    def test_flag(self):
        r = classify_location_relations("Entering the forge served as the assignment")
        assert r.get("R12_AUTHORITATIVE_ROLE_OBSERVABILITY_COMPLETE") is True
        m = r["LOCATION_RELATION_MENTIONS"][0]
        for k in (
            "LOCATION_ROLE", "PRE_ROLE_BIND_CANDIDATE", "FINAL_BIND_ALLOWED",
            "FINAL_BIND_REASON", "LEGACY_BIND_OVERRIDE", "EVENT_REALIZATION",
            "ACCESS_RESULT", "BIND_ALLOWED",
        ):
            assert k in m
