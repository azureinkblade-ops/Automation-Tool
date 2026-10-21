"""R19 semantic relation layer unit gate (shadow only)."""
import json
import re
import unittest
from pathlib import Path

from tools import semantic_relation_layer_r19 as G
from tools import semantic_event_parser_r16 as P16
from tools import single_parse_event_graph_r18 as R18

DEP = ["Kai", "Marta", "Liang", "Kael", "Mira", "Jarek", "Wen", "Sela"]
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "semantic_relation_layer_r19.py"
RES = ROOT / "tools" / "semantic_relation_resources_r19.json"


def rec(text, head, dep=DEP):
    for r in G.analyze(text, depicted_characters=dep)["records"]:
        if r["HEAD"] == head:
            return r
    raise AssertionError((text, head))


def binds(text, head, dep=DEP):
    return rec(text, head, dep)["FINAL_BIND_ALLOWED"]


def rel(text, head, dep=DEP):
    return rec(text, head, dep)["SEMANTIC_RELATION"]


class Architecture(unittest.TestCase):
    def test_no_parse_in_layer(self):
        s = SRC.read_text(encoding="utf-8")
        for bad in ("nlp(", ".pipe(", "get_nlp", "vector", "_BIND_ROLES"):
            self.assertNotIn(bad, s)
        self.assertEqual(len(re.findall(r"FINAL_BIND_ALLOWED\"\]\s*=(?!\s*_new_bind)", s)), 0)

    def test_single_parse(self):
        t = "Kai crossed into the hall and sat down. Mira read in the library."
        P16._DOC_CACHE.pop(t, None)
        n0 = R18.STATS["NLP_CALLS"]
        G.analyze(t, depicted_characters=DEP)
        self.assertEqual(R18.STATS["NLP_CALLS"] - n0, 1)

    def test_resource_cap_and_mode(self):
        d = json.loads(RES.read_text(encoding="utf-8-sig"))
        self.assertEqual(d["MODE"], "CLASSIFICATION_AND_SUPPRESSION_ONLY")
        self.assertLessEqual(G.SEMANTIC_RESOURCE_ENTRY_COUNT + 6, 100)

    def test_relation_classes(self):
        self.assertEqual(len(G.RELATION_CLASSES), 14)
        for r in G.analyze("Kai stared at the hall and Mira read in the library.", depicted_characters=DEP)["records"]:
            self.assertIn(r["SEMANTIC_RELATION"], G.RELATION_CLASSES)


class Boundary(unittest.TestCase):
    def test_gate_of_x(self):
        self.assertFalse(binds("Jarek rapped on the gate of the foundry.", "foundry"))
        self.assertFalse(binds("Jarek rapped on the gate of the foundry.", "gate"))
        self.assertEqual(rel("Jarek rapped on the gate of the foundry.", "foundry"), "BOUNDARY_INTERACTION")

    def test_x_s_gate(self):
        self.assertFalse(binds("Kael waited at the warehouse's gate.", "warehouse"))

    def test_through_gate_into_x(self):
        self.assertTrue(binds("Kai passed through the gate into the hall.", "hall"))

    def test_bare_gate_not_suppressed(self):
        self.assertTrue(binds("Kai waited at the gate.", "gate"))


class Occupancy(unittest.TestCase):
    def test_examples(self):
        for t, h in [("Kai snacked inside the cafe.", "cafe"), ("Mira audited books in the hangar.", "hangar"),
                     ("Wen knitted in the pavilion.", "pavilion"), ("Kael repaired fuses on the skybridge.", "skybridge"),
                     ("Kai sorted receipts at the cafe.", "cafe")]:
            self.assertTrue(binds(t, h), t)


class Transaction(unittest.TestCase):
    def test_examples(self):
        for t, h in [("Kai paid the rent on the office.", "office"), ("Liang sold the lease on the shrine.", "shrine"),
                     ("Mira invested in the chamber.", "chamber"), ("Sela bought shares in the workshop.", "workshop"),
                     ("Kai discussed property at the cafe.", "cafe")]:
            self.assertFalse(binds(t, h), t)
            self.assertIn(rel(t, h), ("TRANSACTION_REFERENCE", "OBJECT_REFERENCE"), t)


class Perception(unittest.TestCase):
    def test_examples(self):
        for t, h in [("Kai stared at the hall.", "hall"), ("Sela peeked at the tunnel.", "tunnel"), ("Mira pointed at the pod.", "pod"),
                     ("Kai jerked his chin at the cafe.", "cafe"), ("Kai looked toward the hall.", "hall"), ("Kai glanced at the hall.", "hall")]:
            self.assertFalse(binds(t, h), t)
            self.assertEqual(rel(t, h), "PERCEPTION_TARGET", t)


class Cessation(unittest.TestCase):
    def test_examples(self):
        for t, h in [("Mira ceased trading in the chamber.", "chamber"), ("Kai stopped working in the cafe.", "cafe"),
                     ("Kai no longer lived in the cafe.", "cafe"), ("Jarek had quit operating in the foundry.", "foundry"),
                     ("Liang gave up sketching in the pavilion.", "pavilion")]:
            self.assertFalse(binds(t, h), t)
            self.assertEqual(rel(t, h), "CESSATION", t)


class Motion(unittest.TestCase):
    def test_completed(self):
        for t, h in [("Kai swam into the room.", "room"), ("Sela snuck through the foundry.", "foundry"),
                     ("Wen slunk into the pavilion.", "pavilion"), ("Kai ducked inside the hall.", "hall"),
                     ("Kai came sprinting into the cafe.", "cafe")]:
            self.assertTrue(binds(t, h), t)
            self.assertEqual(rel(t, h), "COMPLETED_TRAVERSAL", t)

    def test_unrealized(self):
        for t, h in [("Kai hurried to duck into the hall.", "hall"), ("Kai tried to slip into the hall.", "hall"),
                     ("Kai was preparing to enter the hall.", "hall"), ("Mira rushed to barrel into the hangar.", "hangar")]:
            self.assertFalse(binds(t, h), t)


class Permission(unittest.TestCase):
    def test_permission_only(self):
        self.assertFalse(binds("Kai was allowed to enter the hall.", "hall"))
        self.assertEqual(rel("Kai was allowed to enter the hall.", "hall"), "PERMISSION")
        self.assertFalse(binds("Kael was given the all-clear to enter the pod.", "pod"))

    def test_permission_completion(self):
        self.assertTrue(binds("Kael was given the all-clear to enter the pod and ducked inside.", "pod"))


class Denial(unittest.TestCase):
    def test_examples(self):
        for t, h in [("Sela crossed the yard to the square but was shown the door.", "square"),
                     ("Kai walked to the cafe but was turned away.", "cafe"),
                     ("Kai approached the cafe and was refused admission.", "cafe"),
                     ("Kai went to the cafe and was sent back.", "cafe"), ("Kai was barred from entering the cafe.", "cafe")]:
            self.assertFalse(binds(t, h), t)
            self.assertEqual(rel(t, h), "DENIAL", t)

    def test_denial_other_subject_no_cancel(self):
        self.assertTrue(binds("Kai slipped into the cafe and Mira was turned away.", "cafe"))


class Subjects(unittest.TestCase):
    def test_kael_only(self):
        t = "Kael waited outside the warehouse while Wen worked inside the pavilion."
        self.assertFalse(binds(t, "pavilion", dep=["Kael"]))
        self.assertFalse(binds(t, "warehouse", dep=["Kael"]))

    def test_unresolved_pronoun(self):
        self.assertFalse(binds("They slipped into the tower.", "tower", dep=["Kael"]))

    def test_unknown(self):
        self.assertFalse(binds("Kai owned the cafe.", "cafe"))


if __name__ == "__main__":
    unittest.main()
