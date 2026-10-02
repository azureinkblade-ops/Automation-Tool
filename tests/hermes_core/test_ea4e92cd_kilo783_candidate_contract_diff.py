"""Static Kilo 7.8.3 successor impact; no receiver or model execution."""

import hashlib
import json
from pathlib import Path
import sys

from tests.hermes_core.test_ea4e34b_kilo_successor_contract_roll import _current_ids
from tools.hermes_core import kilo_adapter as adapter
from tools.hermes_core import kilo_successor_binding as binding
from tools.hermes_core.hashing import sha256_payload


EXTENSION = Path(r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.8.3-win32-x64")
CANDIDATE_PATH = str(EXTENSION / "bin" / "kilo.exe")
CANDIDATE_SHA256 = "8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a"
CANDIDATE_VERSION = "7.8.3"
CANDIDATE_SIZE = 175349592
CANDIDATE_TRANSPORT = "b9836a346bf73d8c6af62539164aa88c3ea373600e7ee1a73b241da4774a4543"
CANDIDATE_BINDING = "23872196c03dce605ea3f2e0a3b58b75e93a6ae2d254bff0992fb8934248e76e"
CANDIDATE_IDS = {
    "EA-4E.6": "b044f6a703d6ca4a2b94bead81b07a05e4b52948a40ad40e1565db4d2598ebc4",
    "EA-4E.7": "a79c2e9b9b268fedd5595114bf9aeb1ebca44b7726eaae023e3ef951ed193e6d",
    "EA-4E.8": "94ec4047b30498a6dbf4266d44ddb43a90dc65ac3b2582b4ce273e404f0e422f",
    "EA-4E.11": "7c594aa0dcf6107010a17230bbf43a225a9a65022ba345617ce7165d059dc363",
    "EA-4E.14": "fc60a3794980c7cecb983c9303961eb217a99c199c3baa318e44f4d4fc7fa171",
    "EA-4E.17": "fb60c0a4a6471aedb748258931ec06fc87dd980adbcf5503ea772e55d12ed430",
    "EA-4E.18": "25ec6a8940c302c8803d0d72b3058478fb3a55c078db2dbd2a5313cd1211b5e7",
    "EA-4E.21": "9589badd010b0433cf1aece4cad70626d7f5525673dedcc8c98f495cffc07d70",
    "EA-4E.22": "09dc4dd1768a18fcf5cb1680ad2736272f0be5d79fd6f31bc64d47821d36402c",
    "EA-4E.23": "a64ec10512a1e714f06b40b7597efbcf63fb625e2702fe8b1f120c5cc6d19a49",
    "EA-4E.26": "23baa20906675865c4c10028b181b5ddadd9cb218eebc599a28030877306cdd6",
    "EA-4E.28": "3a5f0bff52dafd3fb68cfbd483803634c44c68f8f79fbad6a24fcbf15141eda1",
    "EA-4E.29": "7711cbec4f094f9e3e2df5aa6f6b2d6860c9db28a4f40a8ce9cc5935233390b6",
}


def test_candidate_file_and_manifest_identity_are_exact():
    binary = Path(CANDIDATE_PATH)
    manifest = EXTENSION / "package.json"
    assert binary.is_file() and manifest.is_file()
    assert binary.stat().st_size == CANDIDATE_SIZE
    digest = hashlib.sha256()
    with binary.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    assert digest.hexdigest() == CANDIDATE_SHA256
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    assert (metadata["name"], metadata["publisher"], metadata["version"]) == (
        "kilo-code", "kilocode", CANDIDATE_VERSION)


def candidate_ids(monkeypatch):
    old_transport = adapter.KILO_TRANSPORT_CONTRACT_ID
    old_path = adapter.PINNED_KILO_PATH
    old_hash = adapter.PINNED_KILO_SHA256
    old_version = adapter.PINNED_KILO_VERSION
    old_binding = binding.KILO_EXECUTABLE_SUCCESSOR_BINDING_ID

    old_material = adapter._canonical_material(old_hash, old_version)
    candidate_material = adapter._canonical_material(
        CANDIDATE_SHA256, CANDIDATE_VERSION, binary_path=CANDIDATE_PATH)
    assert {key for key in old_material if old_material[key] != candidate_material[key]} == {
        "binary_path", "binary_sha256", "binary_version"}
    candidate_transport = sha256_payload(candidate_material)
    assert candidate_transport == CANDIDATE_TRANSPORT

    successor = binding.kilo_executable_successor_binding_material()
    successor.update({
        "executable_version": CANDIDATE_VERSION,
        "executable_path": CANDIDATE_PATH,
        "executable_sha256": CANDIDATE_SHA256,
        "transport_contract_id": candidate_transport,
        "predecessor_executable_version": old_version,
        "predecessor_transport_contract_id": old_transport,
    })
    candidate_binding = sha256_payload(successor)
    assert candidate_binding == CANDIDATE_BINDING

    def replace_aliases(old, new):
        for name, module in tuple(sys.modules.items()):
            if module is None or not name.startswith("tools.hermes_core"):
                continue
            for attribute, value in tuple(vars(module).items()):
                if (not attribute.startswith(("HISTORICAL", "LEGACY"))
                        and isinstance(value, str) and value == old):
                    monkeypatch.setattr(module, attribute, new)

    for module in tuple(sys.modules.values()):
        if module is None:
            continue
        receivers = getattr(module, "QUALIFIED_RECEIVERS", None)
        if isinstance(receivers, dict) and "kilo-cli-agent" in receivers:
            monkeypatch.setitem(
                receivers["kilo-cli-agent"], "transport_contract_id", candidate_transport)
    for old, new in (
        (old_transport, candidate_transport),
        (old_path, CANDIDATE_PATH),
        (old_hash, CANDIDATE_SHA256),
        (old_version, CANDIDATE_VERSION),
        (old_binding, candidate_binding),
    ):
        replace_aliases(old, new)
    for key, attribute in (
        ("EA-4E.17", "CURRENT_EA4E17_ISSUANCE_CONTRACT_ID"),
        ("EA-4E.21", "CURRENT_EA4E21_BINDING_CONTRACT_ID"),
        ("EA-4E.22", "CURRENT_EA4E22_INTEGRATION_CONTRACT_ID"),
    ):
        replace_aliases(getattr(binding, attribute), _current_ids()[key])
    return _current_ids()


def test_candidate_rotates_only_sealed_chain(monkeypatch):
    old_ids = _current_ids()
    assert adapter.PINNED_KILO_VERSION == "7.7.9"
    current_model = binding.KILO_MODEL_BINDING_ID
    new_ids = candidate_ids(monkeypatch)
    assert new_ids == CANDIDATE_IDS
    assert set(new_ids) == set(old_ids)
    assert all(new_ids[key] != old_ids[key] for key in old_ids)
    assert binding.KILO_MODEL_BINDING_ID == current_model
