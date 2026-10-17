"""R18 single-parse event graph unit gate (shadow only)."""
import re
import unittest
from pathlib import Path

from tools import single_parse_event_graph_r18 as G
from tools import semantic_event_parser_r16 as P16

DEP = ["Kai", "Marta", "Liang", "Kael", "Mira", "Jarek", "Wen", "Sela"]
SRC = Path(__file__).resolve().parents[1] / "tools" / "single_parse_event_graph_r18.py"


def recs(text, dep=DEP):
    return G.analyze(text, depicted_characters=dep)["records"]


def rec(text, head, dep=DEP):
    for r in recs(text, dep):
        if r["HEAD"] == head:
            return r
    raise AssertionError("no record for %s in %r" % (head, text))


def binds(text, head, dep=DEP):
    return rec(text, head, dep)["FINAL_BIND_ALLOWED"]


class P1Preservation(unittest.TestCase):
    def test_single_bind_point(self):
        s = SRC.read_text(encoding="utf-8")
        self.assertNotIn("_BIND_ROLES", s)
        self.assertNotIn("LEGACY_OVERRIDE", s)
        self.assertEqual(len(re.findall(r"FINAL_BIND_ALLOWED\"\]\s*=(?!\s*_new_bind)", s)), 0)

    def test_shadow_flags(self):
        out = G.analyze("Kai stood in the hall.", depicted_characters=DEP)
        self.assertTrue(out["R18_SHADOW_MODE"])
        self.assertFalse(out["PRODUCTION_CUTOVER"])
        self.assertEqual(G.EVENT_COMPOSITION_KEY, "SUBJECT_PLUS_LOCATION")

    def test_r16_untouched_import(self):
        self.assertEqual(G.R16.__name__, "tools.semantic_event_parser_r16")


class P2Graph(unittest.TestCase):
    def test_graph_edges(self):
        g = G.analyze("Kael waited outside the gate while Wen worked inside the tower.", depicted_characters=DEP)["graph"][0]
        kinds = {e[2] for e in g["EDGES"]}
        self.assertIn("SUBORDINATE_TO", kinds)
        self.assertIn("SUBJECT_OF", kinds)
        self.assertIn("LOCATION_OF", kinds)

    def test_conjunction_same_subject(self):
        g = G.analyze("Kael reached the gate and slipped inside.", depicted_characters=DEP)["graph"][0]
        kinds = {e[2] for e in g["EDGES"]}
        self.assertIn("CONJUNCT_OF", kinds)
        self.assertIn("SAME_SUBJECT", kinds)


class P4Succession(unittest.TestCase):
    def test_all_clear_ducked_inside(self):
        self.assertTrue(binds("Kael was given the all-clear to enter the Nexus Pod and ducked inside.", "pod"))

    def test_cleared_then_strode_in(self):
        self.assertTrue(binds("Kael was cleared to enter the Nexus Pod, then strode in.", "pod"))

    def test_permission_before_slipping_inside(self):
        self.assertTrue(binds("Wen received permission for the jade pavilion before slipping inside.", "pavilion"))

    def test_waited_approval_passed_through(self):
        self.assertTrue(binds("Kael waited for approval at the Nexus Pod and later passed through.", "pod"))

    def test_permission_alone_no_bind(self):
        self.assertFalse(binds("Kai was given clearance to enter the System Hall.", "hall"))


class P5Ellipsis(unittest.TestCase):
    def test_other_subject_blocks(self):
        self.assertFalse(binds("Kael was cleared to enter the Nexus Pod and Wen strode in.", "pod"))

    def test_contrast_other_subject_blocks(self):
        self.assertFalse(binds("Kael was cleared to enter the Nexus Pod, but Mira strode in.", "pod"))

    def test_planned_chain_no_bind(self):
        self.assertFalse(binds("Kael wanted to enter the Nexus Pod and stride in.", "pod"))


class P6Failure(unittest.TestCase):
    def test_bell_shooed(self):
        r = rec("Sela rang the bell at the foundry but was shooed away.", "foundry")
        self.assertEqual(r["LOCATION_ROLE"], "FAILED_DESTINATION")
        self.assertFalse(r["FINAL_BIND_ALLOWED"])

    def test_reached_turned_away(self):
        self.assertFalse(binds("Kael reached the Nexus Pod but was turned away.", "pod"))

    def test_bell_alone_boundary(self):
        r = rec("Sela rang the bell at the foundry.", "foundry")
        self.assertEqual(r["LOCATION_ROLE"], "BOUNDARY_SITE")
        self.assertEqual(r.get("BOUNDARY_RELATION"), "BOUNDARY_INTERACTION")
        self.assertFalse(r["FINAL_BIND_ALLOWED"])


class P7P8Occupancy(unittest.TestCase):
    def test_snacked_inside(self):
        self.assertTrue(binds("Sela snacked inside the undercity tunnel.", "tunnel"))

    def test_audited_books(self):
        self.assertTrue(binds("Mira audited the books in the cargo hangar.", "hangar"))

    def test_sorted_receipts(self):
        self.assertTrue(binds("Jarek sorted receipts at the forge.", "forge"))

    def test_read_quietly(self):
        self.assertTrue(binds("Liang read quietly in the sect library.", "library"))

    def test_sold_lease_no_bind(self):
        self.assertFalse(binds("Liang sold the lease on the mountain shrine.", "shrine"))


class P9Perception(unittest.TestCase):
    def test_peeked(self):
        self.assertFalse(binds("Sela peeked at the undercity tunnel.", "tunnel"))

    def test_stared(self):
        self.assertFalse(binds("Kai stared at the System Hall.", "hall"))

    def test_pointed(self):
        self.assertFalse(binds("Mira pointed at the watchtower.", "watchtower") if False else binds("Mira pointed at the tower.", "tower"))

    def test_frowned(self):
        self.assertFalse(binds("Jarek frowned at the forge.", "forge"))

    def test_homing(self):
        self.assertFalse(binds("Liang was homing in on the mountain shrine.", "shrine"))


class P10Motion(unittest.TestCase):
    def test_swam_into(self):
        self.assertTrue(binds("Kai swam into the training room.", "room"))

    def test_snuck_through(self):
        self.assertTrue(binds("Sela snuck through the foundry.", "foundry"))

    def test_slunk_into(self):
        self.assertTrue(binds("Wen slunk into the jade pavilion.", "pavilion"))


class P11Infinitive(unittest.TestCase):
    def test_hurried_to_duck(self):
        r = rec("Kai hurried to duck into the System Hall.", "hall")
        self.assertIn(r["EVENT_STATE"], ("ATTEMPTED", "IN_PROGRESS"))
        self.assertFalse(r["FINAL_BIND_ALLOWED"])

    def test_tried_to_cross(self):
        self.assertFalse(binds("Kai tried to cross into the System Hall.", "hall"))

    def test_hurried_inside(self):
        self.assertTrue(binds("Kai hurried inside the System Hall.", "hall"))

    def test_crossed_into(self):
        self.assertTrue(binds("Kai crossed into the System Hall.", "hall"))

    def test_managed_to(self):
        self.assertTrue(binds("Kai managed to slip into the System Hall.", "hall"))


class P12Embedding(unittest.TestCase):
    def test_conditional_no_bind(self):
        self.assertFalse(binds("If Wen slunk into the jade pavilion, Kai would follow.", "pavilion"))

    def test_complement_no_bind(self):
        self.assertFalse(binds("Kai said that he slept in the System Hall.", "hall"))

    def test_while_both(self):
        t = "Sela gamed in the foundry while she slunk through the undercity tunnel without a sound."
        self.assertTrue(binds(t, "foundry"))


class P13P14Subject(unittest.TestCase):
    def test_kael_only_still(self):
        t = "Kael waited outside the Nexus Pod while Wen worked inside the jade pavilion."
        self.assertFalse(binds(t, "pavilion", dep=["Kael"]))
        self.assertFalse(binds(t, "pod", dep=["Kael"]))

    def test_unresolved_pronoun(self):
        self.assertFalse(binds("They slipped into the tower.", "tower", dep=["Kael"]))

    def test_unknown_neutral(self):
        self.assertFalse(binds("Kai owned the corner cafe.", "cafe"))


class R18Packet(unittest.TestCase):
    def test_single_parse_count(self):
        t = "Kael waited outside the gate while Wen worked inside the tower. Kai crossed into the hall and sat down."
        P16._DOC_CACHE.pop(t, None)
        before = dict(G.STATS)
        out = G.analyze(t, depicted_characters=DEP)
        self.assertEqual(out["SPACY_PARSE_COUNT"], 1)
        self.assertEqual(out["CLAUSE_REPARSE_COUNT"], 0)
        self.assertEqual(G.STATS["NLP_CALLS"] - before["NLP_CALLS"], 1)
        self.assertEqual(G.STATS["SENTENCES_PARSED"] - before["SENTENCES_PARSED"], 2)

    def test_no_nlp_call_in_source(self):
        s = SRC.read_text(encoding="utf-8")
        self.assertNotIn("nlp(", s)
        self.assertNotIn(".pipe(", s)
        self.assertNotIn("get_nlp", s)

    def test_ontology_single_resource_suppression_only(self):
        s = SRC.read_text(encoding="utf-8")
        for w in ("doorbell", "knocker", "bellpull", "intercom", "buzzer"):
            self.assertNotIn(w, s)
        self.assertEqual(G.BOUNDARY_DEVICE_ONTOLOGY_MODE, "SUPPRESSION_ONLY")

    def test_devices(self):
        for t in ("Sela pressed the buzzer at the foundry.", "Sela used the intercom at the foundry.",
                  "Sela tugged the bellpull at the foundry.", "Sela rang the bell at the foundry."):
            r = rec(t, "foundry")
            self.assertEqual(r["LOCATION_ROLE"], "BOUNDARY_SITE", t)
            self.assertFalse(r["FINAL_BIND_ALLOWED"])
            self.assertFalse(r.get("CURRENT_OCCUPANCY_EVIDENCE"))

    def test_device_never_creates_bind(self):
        self.assertTrue(binds("Sela rang the bell and slipped into the foundry.", "foundry"))

    def test_let_herself_in(self):
        self.assertTrue(binds("Mira was given the all-clear for the cargo hangar and let herself in.", "hangar"))

    def test_permission_then_slipped(self):
        self.assertTrue(binds("Wen received permission for the jade pavilion, then slipped inside.", "pavilion"))

    def test_approach_refused(self):
        self.assertFalse(binds("Kael approached the Nexus Pod and was refused.", "pod"))

    def test_sat_knitting(self):
        self.assertTrue(binds("Liang sat knitting in the jade pavilion.", "pavilion"))

    def test_repaired_equipment_at(self):
        self.assertTrue(binds("Kael repaired equipment at the station.", "station"))

    def test_paid_rent_on(self):
        self.assertFalse(binds("Kai paid the rent on the office.", "office"))

    def test_jerked_chin(self):
        self.assertFalse(binds("Kai jerked his chin at the cafe.", "cafe"))

    def test_looked_toward(self):
        self.assertFalse(binds("Kai looked toward the hall.", "hall"))

    def test_glanced(self):
        self.assertFalse(binds("Kai glanced at the hall.", "hall"))

    def test_came_sprinting(self):
        self.assertTrue(binds("Kai came sprinting into the cafe.", "cafe"))

    def test_serial_cross_subject(self):
        t = "Kai came limping into the cafe when Marta went racing through the room."
        self.assertFalse(binds(t, "room", dep=["Kai"]))

    def test_way_construction(self):
        self.assertTrue(binds("Kai elbowed his way into the hall.", "hall"))

    def test_tried_to_slip(self):
        self.assertFalse(binds("Kai tried to slip inside the hall.", "hall"))

    def test_slipped_inside(self):
        self.assertTrue(binds("Kai slipped inside the hall.", "hall"))

    def test_never_sat_knitting(self):
        self.assertFalse(binds("Liang never sat knitting in the jade pavilion.", "pavilion"))

    def test_embedding_invariance(self):
        base = "Mira audited the books in the hangar"
        self.assertTrue(binds(base + ".", "hangar"))
        for c in ("while", "until", "after", "before", "although", "because", "when"):
            self.assertTrue(binds(base + " " + c + " Kai slept.", "hangar"), c)
        for c in ("but", "and", "yet", "then"):
            self.assertTrue(binds(base + " " + c + " Kai slept.", "hangar"), c)


class R18Reporting(unittest.TestCase):
    def test_fronted_report_stays_nonrealis(self):
        self.assertFalse(binds("Kai slept in the hall, Mira insisted.", "hall"))


if __name__ == "__main__":
    unittest.main()

