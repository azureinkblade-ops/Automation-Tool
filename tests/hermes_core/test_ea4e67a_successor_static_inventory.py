"""Static successor inventory only; no Hermes imports or executable launches."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXTENSION = Path(r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.2-win32-x64")
EXPECTED_HASH = "3dca5f2eb8cc2d875e8cdef756f77347d4899247c318bf2a018d39e0184455cd"


def test_successor_binary_identity():
    binary = EXTENSION / "bin" / "kilo.exe"
    assert binary.stat().st_size == 174145024
    with binary.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == EXPECTED_HASH


def test_extension_version_is_manifest_metadata():
    manifest = json.loads((EXTENSION / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "7.7.2"
    assert manifest["publisher"] == "kilocode"


def test_current_pin_is_exact_and_original_pin_is_retained_as_history():
    source = (ROOT / "tools/hermes_core/kilo_adapter.py").read_text(encoding="utf-8")
    assert 'PINNED_KILO_VERSION = "7.7.2"' in source
    assert EXPECTED_HASH in source
    history = (ROOT / "tools/hermes_core/kilo_successor_binding.py").read_text(encoding="utf-8")
    assert "HISTORICAL_KILO_7_6_2_SHA256" in history
    assert "5d54b522d8a59228951d141cd70438c29115963ecb38d7cdfcf313f59c0f865b" in history


def test_router_depends_on_transport_identity():
    source = (ROOT / "tools/hermes_core/receiver_router.py").read_text(encoding="utf-8")
    assert '"transport_contract_id": KILO_TRANSPORT_CONTRACT_ID' in source


def test_authority_and_issuance_depend_on_router_identity():
    for filename in ("receiver_dispatch.py", "production_issuance.py"):
        source = (ROOT / "tools/hermes_core" / filename).read_text(encoding="utf-8")
        assert '"router_contract_id": compute_ea4e6_router_contract_id()' in source
