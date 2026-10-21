"""R16 semantic event parser tests (shadow only; R15 module untouched)."""
import os
import pytest

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
from tools import semantic_event_parser_r16 as r16
from tools.location_relation_r6 import _BIND_ROLES

DEP = ["Kai", "Marta", "Liang", "Kael", "Mira", "Wen"]


def recs(text, dep=DEP):
    return r16.analyze(text, depicted_characters=dep)["records"]


def rec(text, head, dep=DEP):
    r = [x for x in recs(text, dep) if x["HEAD"] == head]
    assert r, (text, head)
    return r[-1]


def binds(text, head, dep=DEP):
    return rec(text, head, dep)["LOCATION_ROLE"] in _BIND_ROLES


# ---- P2 completed motion (structural, no verb list)
@pytest.mark.parametrize("s,h", [
    ("Kai shuffled into the attic.", "attic"),
    ("Marta barreled into the warehouse.", "warehouse"),
    ("Liang waltzed inside the shrine.", "shrine"),
    ("Kai drifted into the hallway.", "hallway"),
    ("Wen tiptoed into the library.", "library"),
])
def test_p2_completed_motion_binds(s, h):
    r = rec(s, h)
    assert r["LOCATION_ROLE"] == "SUCCESSFUL_DESTINATION" and r["EVENT_STATE"] == "COMPLETED"


@pytest.mark.parametrize("s,h", [
    ("The cart rolled into the hangar.", "hangar"),
    ("The smoke drifted into the hallway.", "hallway"),
    ("Kai would shuffle into the attic.", "attic"),
    ("Kai was shuffling into the attic.", "attic"),
    ("Kai poured the cider into the basement.", "basement"),
    ("Kai never shuffled into the attic.", "attic"),
])
def test_p2_motion_negative_controls(s, h):
    assert not binds(s, h)


# ---- P3 ordinary activity occupancy
@pytest.mark.parametrize("s,h", [
    ("Liang ate his rice in the kitchen.", "kitchen"),
    ("Kai scrolled his phone on the bus.", "bus"),
    ("Kai dozed quietly in the cabin.", "cabin"),
    ("Mira knitted in the attic.", "attic"),
])
def test_p3_activity_binds(s, h):
    assert rec(s, h)["LOCATION_ROLE"] == "CURRENT_SITE"


@pytest.mark.parametrize("s,h", [
    ("The kitchen.", "kitchen"),
    ("Kai on the skybridge.", "skybridge"),
    ("Kai put the book in the library.", "library"),
    ("Kai lost faith in the temple.", "temple"),
    ("The lamps flickered in the hallway.", "hallway"),
])
def test_p3_no_bind_from_location_phrase_alone(s, h):
    assert not binds(s, h)


# ---- P4 object-attachment recovery
@pytest.mark.parametrize("s,h", [
    ("Kai restrung the bow in the workshop.", "workshop"),
    ("Marta polished the brass at the foundry.", "foundry"),
])
def test_p4_object_pp_recovered(s, h):
    r = rec(s, h)
    assert r["LOCATION_ROLE"] == "CURRENT_SITE"


@pytest.mark.parametrize("s,h", [
    ("Kai bought a ticket to the palace.", "palace"),
    ("Kai found the key to the tower.", "tower"),
    ("Kai studied a map of the city.", "city"),
    ("Kai noticed the lamp at the shrine.", "shrine"),
])
def test_p4_noun_complement_not_recovered(s, h):
    assert not binds(s, h)


# ---- P5 perception / communication / memory
@pytest.mark.parametrize("s,h", [
    ("Kai watched the parade at the plaza.", "plaza"),
    ("Kai told Mira about the shrine.", "shrine"),
    ("Kai said that he was in the shrine.", "shrine"),
    ("Kai remembered the evenings in the kitchen.", "kitchen"),
    ("Kai told Mira a story in the kitchen.", "kitchen"),
])
def test_p5_no_occupancy(s, h):
    assert not binds(s, h)


# ---- P6 cessation
@pytest.mark.parametrize("s,h", [
    ("Kai no longer lived in the apartment.", "apartment"),
    ("Kai did not work in the factory anymore.", "factory"),
    ("Kai ceased to sleep in the dungeon.", "dungeon"),
    ("Kai stopped working in the factory.", "factory"),
])
def test_p6_cessation(s, h):
    assert not binds(s, h)


def test_p6_positive_control():
    assert binds("Kai still lived in the apartment.", "apartment")


# ---- P7 completion precedence
@pytest.mark.parametrize("s,h", [
    ("Kai was granted passage into the fortress. He crossed inside.", "fortress"),
    ("Kai was granted passage and entered the fortress.", "fortress"),
    ("Kai was cleared to enter the fortress, then entered.", "fortress"),
])
def test_p7_completion_upgrades(s, h):
    assert rec(s, h)["LOCATION_ROLE"] == "SUCCESSFUL_DESTINATION"


@pytest.mark.parametrize("s,h", [
    ("Kai was granted passage into the fortress.", "fortress"),
    ("Kai was cleared to enter the fortress.", "fortress"),
    ("Kai was granted passage into the fortress. Mira crossed inside.", "fortress"),
])
def test_p7_permission_alone_never_completes(s, h):
    assert not binds(s, h)


# ---- P8 failure precedence
@pytest.mark.parametrize("s,h", [
    ("Kai was allowed toward the fortress but stopped.", "fortress"),
    ("Kai approached the fortress and was turned away.", "fortress"),
])
def test_p8_failure(s, h):
    r = rec(s, h)
    assert r["EVENT_STATE"] == "FAILED" and r["LOCATION_ROLE"] not in _BIND_ROLES


# ---- R15 decisions retained
def test_unresolved_pronoun_fail_neutral():
    r = rec("She knitted in the attic.", "attic")
    assert r["SUBJECT_CHARACTER_ID"] == "UNRESOLVED" and r["LOCATION_ROLE"] not in _BIND_ROLES


def test_cross_subject_nonleak():
    rs = recs("Kai sat in the kitchen while Mira knitted in the attic.", ["Kai"])
    by = {x["HEAD"]: x for x in rs}
    assert by["kitchen"]["LOCATION_ROLE"] == "CURRENT_SITE"
    assert by["attic"]["LOCATION_ROLE"] not in _BIND_ROLES


def test_shadow_only_and_r15_untouched():
    # R15 is a dev-only shadow parser (not in the committed runtime closure); skip explicitly when absent.
    r15 = pytest.importorskip("tools.semantic_event_parser_r15", reason="SKIPPED_DEV_ONLY: tools/semantic_event_parser_r15.py is dev-only and not committed")
    assert r16.PRODUCTION_CUTOVER is False and r15.PARSER_VERSION == "R15.1" and r16.PARSER_VERSION == "R16.0"


# ================= R16 P10-P17 =================
ALL4 = ["Kael", "Mira", "Liang", "Kai", "Jarek", "Wen"]


@pytest.mark.parametrize("s,h", [
    ("Wen slunk into the basement.", "basement"),
    ("Kael crept inside the Nexus Pod.", "pod"),
    ("Jarek strode into the hangar.", "hangar"),
])
def test_p10_tagger_robust_completed_motion(s, h):
    assert binds(s, h, ALL4)


@pytest.mark.parametrize("s,h", [
    ("Kai said Wen slunk into the basement.", "basement"),
    ("If Wen slunk into the basement, Kai would follow.", "basement"),
    ("Wen did not slink into the basement.", "basement"),
    ("Kai was creeping into the tower.", "tower"),
])
def test_p10_irrealis_controls(s, h):
    assert not binds(s, h, ALL4)


@pytest.mark.parametrize("s,h", [
    ("The rain slid into the alley.", "alley"),
    ("The beam swept into the hall.", "hall"),
    ("The rumor spread into the city.", "city"),
    ("The shadow moved into the corridor.", "corridor"),
    ("The cart rolled into the courtyard.", "courtyard"),
])
def test_p11_noncharacter_metaphorical_motion(s, h):
    assert not binds(s, h, ALL4)


@pytest.mark.parametrize("s,h", [
    ("Liang ate rice in the kitchen.", "kitchen"),
    ("Kai scrolled his phone on the bus.", "bus"),
    ("Kael repaired the latch in the apartment.", "apartment"),
    ("Jarek sorted bolts at the forge.", "forge"),
    ("Kael checked the readouts in the chamber.", "chamber"),
])
def test_p12_object_attachment_current(s, h):
    assert binds(s, h, ALL4)


def test_p12_nondepicted_subject_no_bind():
    assert not binds("Jarek sorted bolts at the forge.", "forge", ["Kael"])


@pytest.mark.parametrize("s,h", [
    ("Kael stared at the Nexus Pod.", "pod"),
    ("Kai pointed at the System Hall.", "hall"),
    ("Liang frowned at the ruined sect hall.", "hall"),
    ("Jarek noticed the forge.", "forge"),
    ("Kael talked about Mira's apartment.", "apartment"),
    ("Kai remembered the alley.", "alley"),
])
def test_p13_perception_communication_memory(s, h):
    assert not binds(s, h, ALL4)


@pytest.mark.parametrize("s,h", [
    ("Kael was no longer in the Nexus Pod.", "pod"),
    ("Jarek no longer worked in the forge.", "forge"),
    ("Kai was not inside the System Hall anymore.", "hall"),
    ("Liang had ceased living in the ruined sect hall.", "hall"),
    ("Kai stopped being in the hall.", "hall"),
    ("Kai had left the hall.", "hall"),
    ("Kai was formerly in the hall.", "hall"),
])
def test_p14_cessation(s, h):
    assert not binds(s, h, ALL4)


@pytest.mark.parametrize("s,h", [
    ("Kael waited at the gate until the steward admitted him into the Nexus Pod.", "pod"),
    ("Kael was granted passage and passed through into the Nexus Pod.", "pod"),
    ("Kai was cleared to enter and hurried inside the System Hall.", "hall"),
    ("Liang was allowed to enter, then crossed into the ruined sect hall.", "hall"),
])
def test_p15_completion(s, h):
    assert rec(s, h, ALL4)["LOCATION_ROLE"] == "SUCCESSFUL_DESTINATION"


@pytest.mark.parametrize("s,h", [
    ("Kael was cleared to enter the Nexus Pod but stopped before crossing.", "pod"),
    ("Jarek approached the forge and was turned away.", "forge"),
    ("Kai tried the entrance of the System Hall but could not get through.", "hall"),
])
def test_p15_failure(s, h):
    r = rec(s, h, ALL4)
    assert r["EVENT_STATE"] == "FAILED" and r["LOCATION_ROLE"] not in _BIND_ROLES


@pytest.mark.parametrize("s,h,g", [
    ("Kael sat in the lobby while Mira tried to enter the palace.", "lobby", True),
    ("Kael sat in the lobby while Mira tried to enter the palace.", "palace", False),
    ("Jarek wanted to reach the station, but he slept in the hangar.", "hangar", True),
    ("Jarek wanted to reach the station, but he slept in the hangar.", "station", False),
])
def test_p16_clause_ownership(s, h, g):
    assert binds(s, h, ALL4) is g


def test_p16_cross_subject():
    assert not binds("Kael sat in the lobby while Mira slept in the apartment.", "apartment", ["Kael"])


@pytest.mark.parametrize("s,h", [
    ("Kael and the tower.", "tower"),
    ("The castle loomed over Kai.", "castle"),
    ("Kai owned the cafe.", "cafe"),
    ("Mira lingered near the tower.", "tower"),
])
def test_p17_unknown_neutral(s, h):
    assert not binds(s, h, ALL4)
