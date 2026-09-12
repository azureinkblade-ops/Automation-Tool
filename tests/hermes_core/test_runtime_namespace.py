from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.hermes_core import run_r12e_live_proof as live_proof
from tools.hermes_core.runtime_namespace import (
    HISTORICAL_ORIGINAL_R12E_ID,
    HISTORICAL_R4_ID,
    RUNTIME_NAMESPACE_CONTRACT_VERSION,
    RUNTIME_NAMESPACE_MANIFEST,
    RuntimeNamespaceError,
    RuntimeNamespaceOwner,
    historical_runtime_namespace,
    reserve_runtime_namespace,
    runtime_namespace_path,
)


SOURCE_A = "a" * 40
SOURCE_B = "b" * 40
OWNER_A = RuntimeNamespaceOwner("ea4d4f-r12e-fake-a")
OWNER_B = RuntimeNamespaceOwner("ea4d4f-r12e-fake-b")


class RuntimeNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "runtime" / "ea4d4f"

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_owner_has_same_namespace(self):
        self.assertEqual(
            runtime_namespace_path(self.root, OWNER_A),
            runtime_namespace_path(self.root, OWNER_A),
        )

    def test_restart_reserves_same_namespace_idempotently(self):
        first = reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)
        second = reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)
        self.assertEqual(first.path, second.path)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)

    def test_different_owner_has_different_namespace(self):
        self.assertNotEqual(
            runtime_namespace_path(self.root, OWNER_A),
            runtime_namespace_path(self.root, OWNER_B),
        )

    def test_historical_names_are_preserved(self):
        self.assertEqual(
            historical_runtime_namespace(self.root, HISTORICAL_ORIGINAL_R12E_ID),
            self.root.resolve() / "r12e",
        )
        self.assertEqual(
            historical_runtime_namespace(self.root, HISTORICAL_R4_ID),
            self.root.resolve() / "r12e-r4",
        )

    def test_fresh_owner_never_resolves_to_historical_namespace(self):
        fresh = runtime_namespace_path(self.root, OWNER_A)
        self.assertNotEqual(
            fresh,
            historical_runtime_namespace(self.root, HISTORICAL_ORIGINAL_R12E_ID),
        )
        self.assertNotEqual(
            fresh, historical_runtime_namespace(self.root, HISTORICAL_R4_ID),
        )

    def test_historical_identity_cannot_be_reserved_as_fresh(self):
        for value in (HISTORICAL_ORIGINAL_R12E_ID, HISTORICAL_R4_ID):
            with self.subTest(value=value), self.assertRaises(RuntimeNamespaceError):
                RuntimeNamespaceOwner(value)

    def test_manifest_binds_closed_owner_and_source(self):
        reserved = reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)
        manifest = json.loads(reserved.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["contract_version"], RUNTIME_NAMESPACE_CONTRACT_VERSION)
        self.assertEqual(manifest["proof_identity"], OWNER_A.proof_identity)
        self.assertEqual(manifest["owner_hash"], OWNER_A.owner_hash)
        self.assertEqual(manifest["source_binding"], SOURCE_A)

    def test_different_source_binding_conflicts(self):
        reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)
        with self.assertRaisesRegex(RuntimeNamespaceError, "different material"):
            reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_B)

    def test_foreign_owner_manifest_conflicts(self):
        path = runtime_namespace_path(self.root, OWNER_A)
        path.mkdir(parents=True)
        manifest = {
            "artifact_type": "hermes.runtime_namespace_owner",
            "artifact_version": "1",
            "contract_version": RUNTIME_NAMESPACE_CONTRACT_VERSION,
            "namespace_name": path.name,
            "owner_hash": OWNER_B.owner_hash,
            "owner_type": "governed-qualification-proof",
            "proof_identity": OWNER_B.proof_identity,
            "source_binding": SOURCE_A,
        }
        (path / RUNTIME_NAMESPACE_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeNamespaceError, "different material"):
            reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)

    def test_unknown_ownership_rejected(self):
        runtime_namespace_path(self.root, OWNER_A).mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeNamespaceError, "ownership is unknown"):
            reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)

    def test_unreadable_manifest_rejected(self):
        path = runtime_namespace_path(self.root, OWNER_A)
        path.mkdir(parents=True)
        (path / RUNTIME_NAMESPACE_MANIFEST).write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeNamespaceError, "unreadable"):
            reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)

    def test_terminal_same_owner_replay_preserves_state(self):
        reserved = reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)
        terminal = reserved.path / "live-proof-evidence.json"
        terminal.write_text('{"terminal":true}\n', encoding="utf-8")
        replay = reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)
        self.assertTrue(replay.replayed)
        self.assertEqual(terminal.read_text(encoding="utf-8"), '{"terminal":true}\n')

    def test_reservation_creates_only_owner_manifest(self):
        reserved = reserve_runtime_namespace(self.root, OWNER_A, source_binding=SOURCE_A)
        self.assertEqual(
            [path.name for path in reserved.path.iterdir()],
            [RUNTIME_NAMESPACE_MANIFEST],
        )

    def test_invalid_identity_forms_rejected(self):
        values = (
            "", "../escape", "a..b", "a/b", "a\\b", "C:\\absolute",
            ".hidden", "UPPER",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(RuntimeNamespaceError):
                RuntimeNamespaceOwner(value)

    def test_invalid_source_binding_rejected(self):
        for value in ("", "a" * 39, "a" * 41, "A" * 40, "z" * 40):
            with self.subTest(value=value), self.assertRaises(RuntimeNamespaceError):
                reserve_runtime_namespace(self.root, OWNER_A, source_binding=value)

    def test_live_harness_head_is_valid_source_binding(self):
        reserved = reserve_runtime_namespace(
            self.root, live_proof.RUNTIME_OWNER,
            source_binding=live_proof._git_head(),
        )
        self.assertEqual(reserved.source_binding, live_proof._git_head())

    def test_closed_owner_type_required(self):
        with self.assertRaises(RuntimeNamespaceError):
            runtime_namespace_path(self.root, {"proof_identity": OWNER_A.proof_identity})

    def test_namespace_remains_beneath_trusted_root(self):
        path = runtime_namespace_path(self.root, OWNER_A)
        self.assertIn(self.root.resolve(), path.parents)

    def test_live_harness_uses_fresh_isolated_owner(self):
        self.assertEqual(live_proof.RUNTIME_OWNER.proof_identity, "ea4d4f-r12e-r6-one-shot")
        self.assertEqual(
            live_proof.RUNTIME,
            runtime_namespace_path(live_proof.RUNTIME_ROOT, live_proof.RUNTIME_OWNER),
        )
        self.assertNotEqual(
            live_proof.RUNTIME,
            historical_runtime_namespace(
                live_proof.RUNTIME_ROOT, HISTORICAL_ORIGINAL_R12E_ID,
            ),
        )


if __name__ == "__main__":
    unittest.main()
