"""Static successor inventory only; no Hermes imports or executable launches."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXTENSION = Path(r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.6.2-win32-x64")
EXPECTED_HASH = "5d54b522d8a59228951d141cd70438c29115963ecb38d7cdfcf313f59c0f865b"


def test_successor_binary_identity():
    binary = EXTENSION / "bin" / "kilo.exe"
    assert binary.stat().st_size == 173595648
    with binary.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == EXPECTED_HASH


def test_extension_version_is_manifest_metadata():
    manifest = json.loads((EXTENSION / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "7.6.2"
    assert manifest["publisher"] == "kilocode"


def test_production_pin_has_not_been_substituted():
    source = (ROOT / "tools/hermes_core/kilo_adapter.py").read_text(encoding="utf-8")
    assert 'PINNED_KILO_VERSION = "7.5.16"' in source
    assert EXPECTED_HASH not in source


def test_router_depends_on_transport_identity():
    source = (ROOT / "tools/hermes_core/receiver_router.py").read_text(encoding="utf-8")
    assert '"transport_contract_id": KILO_TRANSPORT_CONTRACT_ID' in source


def test_authority_and_issuance_depend_on_router_identity():
    for filename in ("receiver_dispatch.py", "production_issuance.py"):
        source = (ROOT / "tools/hermes_core" / filename).read_text(encoding="utf-8")
        assert '"router_contract_id": compute_ea4e6_router_contract_id()' in source
