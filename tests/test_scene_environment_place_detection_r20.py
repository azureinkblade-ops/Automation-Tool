"""R20 positive setting ontology / place detection unit gate (shadow only)."""
import json
import re
import unittest
from pathlib import Path

from tools import place_detection_r20 as G
from tools import semantic_event_parser_r16 as P16
from tools import single_parse_event_graph_r18 as R18

DEP = ["kai", "mira", "liang", "kael", "mina", "sera", "varik", "jarek"]
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "place_detection_r20.py"
RES = ROOT / "tools" / "resources" / "setting_nouns_r20.json"


def recs(text, dep=DEP):
    return G.analyze(text, depicted_characters=dep)["records"]


def binds(text, head, dep=DEP):
    return any(r["HEAD"] == head and r["FINAL_BIND_ALLOWED"] for r in recs(text, dep))


def rec(text, head, dep=DEP):
    return next(r for r in recs(text, dep) if r["HEAD"] == head)


class Architecture(unittest.TestCase):
    def test_no_parse_no_bind_table(self):
        s = SRC.read_text(encoding="utf-8")
        for bad in ("nlp(", ".pipe(", "_BIND_ROLES", "vector"):
            self.assertNotIn(bad, s)
        self.assertEqual(len(re.findall(r'\["FINAL_BIND_ALLOWED"\]\s*=\s*(?![\s_]*_new_bind)', s)), 0)

    def test_single_parse(self):
        t = "Mira stood on the terrace and Kai crossed the yard."
        P16._DOC_CACHE.pop(t, None)
        n0 = R18.STATS["NLP_CALLS"]
        G.analyze(t, depicted_characters=DEP)
        self.assertEqual(R18.STATS["NLP_CALLS"] - n0, 1)

    def test_ontology_auditable_capped(self):
        d = json.loads(RES.read_text(encoding="utf-8"))
        self.assertEqual(d["MODE"], "POSITIVE_SETTING_CANDIDATE_ONLY")
        self.assertLessEqual(len(d["ENTRIES"]), 100)
        for e in d["ENTRIES"]:
            self.assertEqual(set(e), {"LEMMA", "SETTING_CLASS", "RATIONALE", "SOURCE"})
            self.assertIn(e["SOURCE"], ("SETTING_DEFINITION", "CALIBRATION_CORPUS"))
            self.assertRegex(e["LEMMA"], r"^[a-z]+$")
        self.assertFalse({e["LEMMA"] for e in d["ENTRIES"]} & set(d["AMBIGUOUS_EXCLUDED"]))


class Positive(unittest.TestCase):
    def test_terrace(self):
        self.assertTrue(binds("Mira stood on the terrace.", "terrace"))

    def test_crosswalk(self):
        self.assertTrue(binds("Mina stood at the crosswalk.", "crosswalk"))

    def test_loft(self):
        self.assertTrue(binds("Kai sat in the loft.", "loft"))

    def test_stairs(self):
        self.assertTrue(binds("Rian stood at the top step of the stairs.", "stairs", dep=["rian"]))

    def test_threshold_binds_itself(self):
        self.assertTrue(binds("Kael stood at the threshold.", "threshold"))

    def test_entry(self):
        self.assertTrue(binds("Kai went to the gym.", "gym"))
        self.assertTrue(binds("Ilya came back to the terrace.", "terrace", dep=["ilya"]))

    def test_named_setting_no_list(self):
        self.assertNotIn("divide", {e["LEMMA"] for e in json.loads(RES.read_text(encoding="utf-8"))["ENTRIES"]} - {"divide"})
        self.assertTrue(binds("Kael stood on the Ashen Divide.", "divide"))

    def test_halted_motion(self):
        self.assertTrue(binds("Kai stopped inside the doorway.", "doorway"))


class Negative(unittest.TestCase):
    def test_local_spots(self):
        for t, h in [("Kai sat on the mat.", "mat"), ("Kai sat at the table.", "table"), ("Jarek sat by the fountain.", "fountain"),
                     ("Kai stood beside Han.", "han")]:
            self.assertFalse(binds(t, h), t)

    def test_ambiguous_neutral(self):
        for t, h in [("Kai stood at the door.", "door"), ("Kai leaned against the wall.", "wall"), ("Kai stood at the edge.", "edge")]:
            self.assertFalse(binds(t, h), t)
            self.assertEqual(rec(t, h)["MENTION_CLASS"], "AMBIGUOUS")

    def test_attempt(self):
        self.assertFalse(binds("Kai tried to reach the terrace.", "terrace"))
        self.assertFalse(binds("Kai hurried to duck into the loft.", "loft"))

    def test_in_progress_and_approach(self):
        self.assertFalse(binds("Kai was walking to the gym.", "gym"))
        self.assertFalse(binds("Kai headed to the gym.", "gym"))

    def test_permission(self):
        self.assertFalse(binds("Kai was allowed to enter the loft.", "loft"))

    def test_denial(self):
        self.assertFalse(binds("Kai was barred from entering the loft.", "loft"))
        self.assertFalse(binds("Kai went to the gym but was turned away.", "gym"))

    def test_negation(self):
        self.assertFalse(binds("Kai never went to the gym.", "gym"))

    def test_subject_gate(self):
        self.assertFalse(binds("Mira stood on the terrace.", "terrace", dep=["kai"]))
        self.assertFalse(binds("She stood on the terrace.", "terrace", dep=["kai"]))
        self.assertFalse(binds("The guard stood on the terrace.", "terrace"))

    def test_perception_carryover(self):
        self.assertFalse(binds("Kai kept glancing at his wristwatch, then at the street, then at the lamp.", "street"))
        self.assertFalse(binds("Kai stared at the terrace.", "terrace"))

    def test_gate_owner_boundary(self):
        self.assertFalse(binds("Jarek rapped on the gate of the foundry.", "foundry"))
        self.assertFalse(binds("Kael waited at the warehouse's gate.", "warehouse"))
        self.assertTrue(binds("Kai passed through the gate into the hall.", "hall"))

    def test_r12_authority(self):
        for r in recs("Mira stood on the terrace and Kai sat on the mat."):
            self.assertEqual(r["FINAL_BIND_ALLOWED"], P16._new_bind(r["LOCATION_ROLE"]))


if __name__ == "__main__":
    unittest.main()
