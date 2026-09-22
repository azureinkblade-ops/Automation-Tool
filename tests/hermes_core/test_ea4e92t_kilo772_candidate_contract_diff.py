"""In-memory Kilo 7.7.2 successor diff; never launch or promote it."""

import json
from pathlib import Path
import runpy
import sys

from tools.hermes_core import kilo_adapter as adapter
from tools.hermes_core import kilo_successor_binding as binding
from tools.hermes_core.hashing import sha256_payload


CANDIDATE_PATH = (
    r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.2-win32-x64\bin\kilo.exe"
)
CANDIDATE_HASH = "3dca5f2eb8cc2d875e8cdef756f77347d4899247c318bf2a018d39e0184455cd"
CANDIDATE_VERSION = "7.7.2"
CANDIDATE_SIZE = 174145024
CANDIDATE_TRANSPORT = "40f23258d1abf1a799747d4ea2899a6103fa5e1fb33384f1c17dd4104ea1c578"
CANDIDATE_BINDING = "cee3f5c96ef344ead9954030b671ae4e387f3a08e6e9df86885aaeafb4106840"
PREDECESSOR_BINDING = "b89f9f02f3e99cf70a98de8b4fb02b545e51855bb7340ed829ece749256b9be1"
PREDECESSOR_IDS = {
    "EA-4E.6": "80dde2cc32d68231fbb018a7799ca32edc5a710f856b8d764758261dc7e0be63",
    "EA-4E.7": "fdc9d48aadeb6353f2fdfed2921904079ff31d045cd56a1c9975c8b91c1f3a61",
    "EA-4E.8": "49d2a5ce10a506f7ea6ac7a1290df298b4058b680ea7b7e953464e94845d7313",
    "EA-4E.11": "f3111551d9be06f8437be9919cc9d7dddca686dfdb360082c9525feb4cfb6123",
    "EA-4E.14": "eb58c9ae1e4ca1fcc6a6fb6ecf321450dbf477b3669a66cab6fa1fa1bafc3473",
    "EA-4E.17": "30c35204bb118b8978e6171ebef11e54fa90c6497c27da786717836af17b62ba",
    "EA-4E.18": "775424531671c999569353d47115b5699802acacaa13d0b2b0743b4a6ce41d35",
    "EA-4E.21": "2dabd852fd943cb13f23986621aac4d59f4b0054a353808ec155e0ff1b24dc5a",
    "EA-4E.22": "8aa6bb3760258d14de1621912072c0374ada91d444f6f51d03648ff4a8e51a3c",
    "EA-4E.23": "6191b758a61848b27068bf8d18b44b91cb0b32eb3e391a58a5ccd3c1908ef9a9",
    "EA-4E.26": "9e3118549e6e26e574b93b81aefd816228722d5feb525cad8a10086ad62a86e0",
    "EA-4E.28": "c6859afb31ffb218cfb09e8f4e6a7f355165bb47fa386d603f0689506ae38d58",
    "EA-4E.29": "11a5230334804d82405994a8ccaa62c0a4a49c2cd01a34854ab75758ba090525",
}
CANDIDATE_IDS = {
    "EA-4E.6": "67435bdb8169cd7973131c5df6e89c5fdd86d9a495a7f428fd681b05db8a7d2e",
    "EA-4E.7": "71a5c8e9feb6c755743292f758fe3a04adef74565f9f56027f904608c6588e54",
    "EA-4E.8": "62dd1a6d7a66a91b7d7348ecdf56925a3285ccbc38da9674a08ed0ec54e4a544",
    "EA-4E.11": "d0d9709ddbb5876599ac19ece28665d0f78721774576afee9934bb665cda0492",
    "EA-4E.14": "fb75980ba6f8812f9cde51977120fb4283987b1badd9047605217b15802ca99e",
    "EA-4E.17": "7e8e6e668791b38e085329dde5c364750b163897caa0cf7977de3985e289203c",
    "EA-4E.18": "1b2cd071de0d8a58d248c8b6c38f9699ffcc729c02909584f45870b901d8a12e",
    "EA-4E.21": "3f159719f0109a43fa3fff9b50f661694aad1e83e06b161f8b5026e4cc050d72",
    "EA-4E.22": "19747974b50bdb400471496c6eae91ae552a296a6b58695324ffd323709961c9",
    "EA-4E.23": "31bc9f5587fa93a770dd32968174c114abc1cc064f513e9b1697772516008b2c",
    "EA-4E.26": "3c9cdd52383a7c28a25638cef5a9f72fa6c7f27fb2ac807d13e7d084f9288576",
    "EA-4E.28": "eaeae2dfda8444596e98b7beb949975d4e05453001af1140c694751f246d351e",
    "EA-4E.29": "64770d93dd04eaaa8149cb4e4bea1f69adbb032b446069dc79850a4ecd2334e9",
}


def test_candidate_contract_diff_is_isolated_and_deterministic(monkeypatch):
    baseline = runpy.run_path(str(
        Path(__file__).with_name("test_ea4e34b_kilo_successor_contract_roll.py")))
    current_ids = baseline["_current_ids"]

    def replace_aliases(old, new):
        for name, module in tuple(sys.modules.items()):
            if module is None or not name.startswith("tools.hermes_core"):
                continue
            for attribute, value in tuple(vars(module).items()):
                if (not attribute.startswith(("HISTORICAL", "LEGACY"))
                        and isinstance(value, str) and value == old):
                    monkeypatch.setattr(module, attribute, new)

    def replace_transport(old, new):
        replace_aliases(old, new)
        for name, module in tuple(sys.modules.items()):
            if module is None or not name.startswith("tools.hermes_core"):
                continue
            receivers = getattr(module, "QUALIFIED_RECEIVERS", None)
            if isinstance(receivers, dict) and "kilo-cli-agent" in receivers:
                monkeypatch.setitem(
                    receivers["kilo-cli-agent"], "transport_contract_id", new)

    old_transport = adapter.KILO_TRANSPORT_CONTRACT_ID
    old_path = adapter.PINNED_KILO_PATH
    old_hash = adapter.PINNED_KILO_SHA256
    old_version = adapter.PINNED_KILO_VERSION
    old_ids = current_ids()
    old_binding = binding.KILO_EXECUTABLE_SUCCESSOR_BINDING_ID

    old_material = adapter._canonical_material(
        old_hash, old_version, binary_path=old_path)
    candidate_material = adapter._canonical_material(
        CANDIDATE_HASH, CANDIDATE_VERSION, binary_path=CANDIDATE_PATH)
    assert {key for key in old_material if old_material[key] != candidate_material[key]} == {
        "binary_path", "binary_sha256", "binary_version"
    }
    candidate_transport = sha256_payload(candidate_material)
    assert candidate_transport != old_transport

    replace_transport(old_transport, candidate_transport)
    replace_aliases(old_path, CANDIDATE_PATH)
    replace_aliases(old_hash, CANDIDATE_HASH)
    replace_aliases(old_version, CANDIDATE_VERSION)
    caches = (
        ("EA-4E.17", "CURRENT_EA4E17_ISSUANCE_CONTRACT_ID"),
        ("EA-4E.21", "CURRENT_EA4E21_BINDING_CONTRACT_ID"),
        ("EA-4E.22", "CURRENT_EA4E22_INTEGRATION_CONTRACT_ID"),
    )
    invocation = sys.modules["tools.hermes_core.production_invocation_authorization"]
    for key, attribute in caches:
        replace_aliases(getattr(binding, attribute), current_ids()[key])
    for _, attribute in caches:
        assert getattr(invocation, attribute) == getattr(binding, attribute)

    new_ids = current_ids()
    successor_material = binding.kilo_executable_successor_binding_material()
    successor_material.update({
        "executable_version": CANDIDATE_VERSION,
        "executable_path": CANDIDATE_PATH,
        "executable_sha256": CANDIDATE_HASH,
        "transport_contract_id": candidate_transport,
        "predecessor_executable_version": old_version,
        "predecessor_transport_contract_id": old_transport,
    })
    new_binding = sha256_payload(successor_material)

    result = {
        "candidate_transport": candidate_transport,
        "candidate_executable_binding": new_binding,
        "predecessor_binding": old_binding,
        "predecessor_contract_ids": old_ids,
        "candidate_contract_ids": new_ids,
    }
    print(json.dumps(result, sort_keys=True))

    assert set(new_ids) == set(old_ids)
    assert all(new_ids[key] != old_ids[key] for key in old_ids)
    assert old_ids == PREDECESSOR_IDS
    assert old_binding == PREDECESSOR_BINDING
    assert candidate_transport == CANDIDATE_TRANSPORT
    assert new_binding == CANDIDATE_BINDING
    assert new_ids == CANDIDATE_IDS
    assert current_ids() == CANDIDATE_IDS
