"""Static bootstrap contract qualification; the JavaScript is never executed."""

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "tools" / "ea4e92s_probe_bootstrap.js"
EXPECTED_SIZE = 6834
EXPECTED_SHA256 = "6884c8745ea18c9195736c48745816c0b8b8e3cbd0be966a089042e6e97df1b2"


def source_bytes():
    return BOOTSTRAP.read_bytes()


def source_text():
    return source_bytes().decode("ascii")


def test_bootstrap_has_frozen_identity_and_repository_provenance():
    content = source_bytes()
    assert len(content) == EXPECTED_SIZE
    assert hashlib.sha256(content).hexdigest() == EXPECTED_SHA256
    assert content.startswith(
        b"// SPDX-License-Identifier: LicenseRef-AzureInkblade-Internal\n")
    assert b"\r" not in content
    assert b"\0" not in content
    assert len(content) < 1024 * 1024


def test_bootstrap_covers_exact_probe_matrix_once():
    text = source_text()
    for number in range(1, 13):
        probe_id = f"NQ-{number:02d}"
        assert text.count(f'"{probe_id}": async') == 1
    assert '"NQ-01": async () => fail("NQ-01 must terminate before resume")' in text


def test_bootstrap_has_exact_cli_and_canonical_request_contract():
    text = source_text()
    required = (
        'argv.length !== 6',
        'argv[0] !== "--probe-id"',
        'argv[2] !== "--request-id"',
        'argv[4] !== "--request"',
        'text !== JSON.stringify(canonical(request))',
        'request.schemaVersion !== 1',
        'request.requestId !== args.requestId',
        'request.probeId !== args.probeId',
        'JSON.stringify(request.budgets) !== JSON.stringify(FIXED_BUDGETS)',
    )
    for marker in required:
        assert marker in text


def test_bootstrap_has_bounded_binary_result_frame():
    text = source_text()
    assert 'header.writeUInt32BE(payload.length, 0)' in text
    assert 'payload.length > 64 * 1024' in text
    assert 'process.stdout.write(header)' in text
    assert 'process.stdout.write(payload)' in text


def test_bootstrap_timeout_and_fixture_contracts_are_self_enforcing():
    text = source_text()
    assert "new Promise(() => setInterval(() => {}, 1000))" in text
    assert '"NQ-08": async () => waitForever()' in text
    assert '"NQ-12": async () => waitForever()' in text
    assert "if (sha256 !== config.sha256)" in text
    assert 'fail("filesystem probe target identity mismatch")' in text


def test_bootstrap_has_only_expected_node_capabilities():
    text = source_text()
    required = {
        'require("node:child_process")',
        'require("node:crypto")',
        'require("node:fs")',
        'require("node:net")',
    }
    assert {line.strip().split(" = ")[1].rstrip(";") for line in text.splitlines()
            if line.startswith("const ") and "require(" in line} == required
    for forbidden in (
            "eval(", "new Function", "node:http", "node:https", "node:tls",
            "node:dns", "fetch(", "WebSocket", "playwright", "selenium",
            "ComfyUI", "CUDA", "OpenAI", "Codex", "Kilo"):
        assert forbidden not in text


def test_bootstrap_does_not_execute_when_imported():
    text = source_text()
    assert "if (require.main === module)" in text
    assert "main(process.argv.slice(2)).catch" in text
    assert "module.exports = Object.freeze" in text


def test_static_test_itself_has_no_process_or_network_capability():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported == {"ast", "hashlib"}
