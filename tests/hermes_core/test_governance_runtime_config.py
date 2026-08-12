"""Runtime governance DB path resolver tests (plan §13, §14).

Pure-path tests: the resolver has NO filesystem side effect, so these run
without creating any directory or DB file.
"""

import os
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core.runtime_config import (
    GovernanceRuntimeConfigError,
    default_governance_db_path,
    resolve_governance_db_path,
)


class ResolveGovernanceDbPathTests(unittest.TestCase):
    def test_override_wins_over_default(self) -> None:
        env = {"HERMES_GOVERNANCE_DB": r"C:\custom\hermes.db"}
        result = resolve_governance_db_path(env)
        self.assertEqual(result, Path(r"C:\custom\hermes.db").resolve())
        self.assertTrue(result.is_absolute())

    def test_default_uses_localappdata(self) -> None:
        env = {"LOCALAPPDATA": r"C:\Users\test\AppData\Local"}
        result = resolve_governance_db_path(env)
        self.assertEqual(
            result, Path(r"C:\Users\test\AppData\Local\Hermes\governance.db").resolve()
        )

    def test_default_is_unaffected_by_override_absence(self) -> None:
        env = {
            "LOCALAPPDATA": r"C:\Users\test\AppData\Local",
            "HERMES_GOVERNANCE_DB": "",
        }
        result = resolve_governance_db_path(env)
        self.assertEqual(
            result, Path(r"C:\Users\test\AppData\Local\Hermes\governance.db").resolve()
        )

    def test_resolver_creates_no_filesystem_entries(self) -> None:
        # Resolution must not touch the filesystem.
        env = {"HERMES_GOVERNANCE_DB": r"C:\nonexistent_dir_x\hermes.db"}
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp) / "should_not_appear"
            env["LOCALAPPDATA"] = str(Path(tmp) / "lap")
            result = resolve_governance_db_path(env)
            self.assertEqual(result, Path(env["HERMES_GOVERNANCE_DB"]).resolve())
            self.assertFalse(sentinel.exists())
            self.assertFalse((Path(tmp) / "lap").exists())

    def test_missing_localappdata_fails_closed(self) -> None:
        with self.assertRaises(GovernanceRuntimeConfigError):
            resolve_governance_db_path({})

    def test_empty_localappdata_fails_closed(self) -> None:
        with self.assertRaises(GovernanceRuntimeConfigError):
            resolve_governance_db_path({"LOCALAPPDATA": "   "})

    def test_relative_override_rejected(self) -> None:
        with self.assertRaises(GovernanceRuntimeConfigError):
            resolve_governance_db_path({"HERMES_GOVERNANCE_DB": "relative/hermes.db"})

    def test_whitespace_override_treated_as_unset(self) -> None:
        env = {
            "LOCALAPPDATA": r"C:\Users\test\AppData\Local",
            "HERMES_GOVERNANCE_DB": "   ",
        }
        result = resolve_governance_db_path(env)
        self.assertEqual(
            result, Path(r"C:\Users\test\AppData\Local\Hermes\governance.db").resolve()
        )

    def test_default_helper_matches_resolver_default(self) -> None:
        env = {"LOCALAPPDATA": r"C:\Users\test\AppData\Local"}
        self.assertEqual(default_governance_db_path(env), resolve_governance_db_path(env))


if __name__ == "__main__":
    unittest.main()
