"""Static Kilo 7.7.9 candidate identity and in-memory contract diff only."""

import hashlib
import json
from pathlib import Path
import sys

from tests.hermes_core.test_ea4e34b_kilo_successor_contract_roll import _current_ids
from tests.hermes_core.test_ea4e92t_kilo772_candidate_contract_diff import (
    CANDIDATE_IDS as PINNED_IDS,
)
from tools.hermes_core import kilo_adapter as adapter
from tools.hermes_core import kilo_successor_binding as binding
from tools.hermes_core.hashing import sha256_payload


EXTENSION = Path(r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.9-win32-x64")
CANDIDATE_PATH = str(EXTENSION / "bin" / "kilo.exe")
CANDIDATE_SHA256 = "9ef2ca9633cece72293d269502bee16720d9179990c1b65abc0599c6d356bd07"
CANDIDATE_VERSION = "7.7.9"
CANDIDATE_SIZE = 175458816
CANDIDATE_TRANSPORT = "b97e4902056689fd7655c75955dcecb906d372b1a7dce012d9d0a1891472be06"
CANDIDATE_BINDING = "653317206aaba6161ff67d2a199ded169daa19869ea578fd4e8ccb2413570ddd"
CANDIDATE_IDS = {
    "EA-4E.6": "d26c3f6dd24c1fa25a1bc963bcdce17c8e5b1255695e10c63abe35d367b24ff2",
    "EA-4E.7": "4bef69cfef38df6a5549062aa60393773c268a734c4cb4e8ee8c929bb9dc91fb",
    "EA-4E.8": "bf1d279545f787ddd347c367c06be3c53f3462f7a253bf26a323ae867cce2156",
    "EA-4E.11": "ff9e72b21a4b905e898ef88b2352a152bc32ad3a63d4e93a25dbb5d8fed13c4d",
    "EA-4E.14": "ccef2473acceccd2548d10791ffdeaabce62c4adcf9be365577e95b6ed31b805",
    "EA-4E.17": "f593677f85599e1a3bcc4956e190c5cfd06cfc5156d9200dc16dad5b31315032",
    "EA-4E.18": "061cb8b52485a035c850ce675aa7025a98fbe18de86739fbe421430afbc3e704",
    "EA-4E.21": "a429da60f529461ad3972b79b68cb1c7e886878aa5fd19d985495df06a265a0f",
    "EA-4E.22": "27c4e7eaa5b894f607a9ec7d1430d686ef38c634874fbfbc2bca87e1ddd8aaf7",
    "EA-4E.23": "d5043df466a2ef61a3d5b9e05eb70fc54cc2dacfa003b0fee705accb241f5fd2",
    "EA-4E.26": "b97251db3f56ab27ecf937eaabc3cd4388b2ad56aaaac47e730c7f924815f92c",
    "EA-4E.28": "379e2edd3673169eb9a86a2e811555bdc437e4f94362a8017eed9163dc587f90",
    "EA-4E.29": "14ce38bad7c0f477239eae3b0342859742f3d69966bde9987807636eb9ef7103",
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
    assert metadata["name"] == "kilo-code"
    assert metadata["publisher"] == "kilocode"
    assert metadata["version"] == CANDIDATE_VERSION


def test_candidate_diff_changes_only_binary_identity_and_sealed_ids(monkeypatch):
    old_ids = _current_ids()
    if adapter.PINNED_KILO_VERSION == CANDIDATE_VERSION:
        assert old_ids == CANDIDATE_IDS
        assert binding.HISTORICAL_EA4E_7_7_2_CONTRACT_IDS == PINNED_IDS
        assert adapter.KILO_TRANSPORT_CONTRACT_ID == CANDIDATE_TRANSPORT
        assert binding.KILO_EXECUTABLE_SUCCESSOR_BINDING_ID == CANDIDATE_BINDING
        return
    assert old_ids == PINNED_IDS
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
                receivers["kilo-cli-agent"], "transport_contract_id",
                candidate_transport)
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
    candidate_ids = _current_ids()
    assert candidate_ids == CANDIDATE_IDS
    assert set(candidate_ids) == set(old_ids)
    assert all(candidate_ids[key] != old_ids[key] for key in old_ids)
    assert binding.KILO_MODEL_BINDING_ID == (
        "b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544")
