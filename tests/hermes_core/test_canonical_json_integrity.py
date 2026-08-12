from __future__ import annotations

import unittest

from tools.hermes_core.hashing import canonical_json


class HermesCanonicalJsonIntegrityTests(unittest.TestCase):
    def test_canonical_json_exact_string(self) -> None:
        payload = {
            "evidence_package_id": "evidence-consensus-disposition-fixture",
            "findings": [],
            "review_ids": [
                "22222222-2222-2222-2222-222222222222",
                "33333333-3333-3333-3333-333333333333",
            ],
            "task_id": "11111111-1111-1111-1111-111111111111",
        }

        expected = (
            '{"evidence_package_id":"evidence-consensus-disposition-fixture",'
            '"findings":[],"review_ids":['
            '"22222222-2222-2222-2222-222222222222",'
            '"33333333-3333-3333-3333-333333333333"],'
            '"task_id":"11111111-1111-1111-1111-111111111111"}'
        )

        self.assertEqual(canonical_json(payload), expected)


if __name__ == "__main__":
    unittest.main()
