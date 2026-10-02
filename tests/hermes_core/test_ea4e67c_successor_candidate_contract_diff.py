"""In-memory candidate contract diff; never promote pins or touch live stores."""

import json
from pathlib import Path
import runpy
import sys

from tools.hermes_core import kilo_adapter as adapter
from tools.hermes_core import kilo_successor_binding as binding
from tools.hermes_core.hashing import sha256_payload


CANDIDATE_PATH = r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.6.2-win32-x64\bin\kilo.exe"
CANDIDATE_HASH = "5d54b522d8a59228951d141cd70438c29115963ecb38d7cdfcf313f59c0f865b"
EXPECTED_IDS = {
    "EA-4E.6": "80dde2cc32d68231fbb018a7799ca32edc5a710f856b8d764758261dc7e0be63",
    "EA-4E.7": "fdc9d48aadeb6353f2fdfed2921904079ff31d045cd56a1c9975c8b91c1f3a61",
    "EA-4E.8": "49d2a5ce10a506f7ea6ac7a1290df298b4058b680ea7b7e953464e94845d7313",
    "EA-4E.11": "f3111551d9be06f8437be9919cc9d7dddca686dfdb360082c9525feb4cfb6123",
    "EA-4E.14": "eb58c9ae1e4ca1fcc6a6fb6ecf321450dbf477b3669a66cab6fa1fa1bafc3473",
    "EA-4E.17": "30c35204bb118b8978e6171ebef11e54fa90c6497c27da786717836af17b62ba",
    "EA-4E.18": "775424531671c999569353d47115b5699802acacaa13d0b2b0743b4a6ce41d35",
    "EA-4E.21": "2dabd852fd943cb13f23986621aac4d59f4b0054a353808ec155e0ff1b24dc5a",
    "EA-4E.22": "8aa6bb3760258d14de1621912072c0374ada91d444f6f51d03648ff4a8e51a3c",
    "EA-4E.23": "e38eb5260102205f2dddf7f104676a40bf02fb24a74251af0afc4de1f84f898c",
    "EA-4E.26": "131b0d2657d5e2be98c053456c2e421aea42a19b01862d3cb59db821833f9eb9",
    "EA-4E.28": "7df75a6034f8906eb65a310a4fbd60b26c2d8a848407883713d0d436193a7eec",
    "EA-4E.29": "dd3b3755946eafdbaea6e5149b8372888b01af6f9768ef37fa54f0660bdb7bef",
}


def test_candidate_contract_diff_is_isolated_and_deterministic(monkeypatch):
    baseline = runpy.run_path(str(Path(__file__).with_name("test_ea4e34b_kilo_successor_contract_roll.py")))
    current_ids = baseline["_current_ids"]
    old_ids = current_ids()
    old_transport = adapter.KILO_TRANSPORT_CONTRACT_ID
    old_path = adapter.PINNED_KILO_PATH
    old_hash = adapter.PINNED_KILO_SHA256
    old_version = adapter.PINNED_KILO_VERSION
    old_material = adapter._canonical_material(old_hash, old_version)
    candidate_material = adapter._canonical_material(CANDIDATE_HASH, "7.6.2", binary_path=CANDIDATE_PATH)
    candidate_transport = sha256_payload(candidate_material)
    assert candidate_transport != old_transport
    assert {key for key in old_material if old_material[key] != candidate_material[key]} == {
        "binary_path", "binary_sha256", "binary_version"
    }

    def replace_aliases(old, new):
        for name, module in tuple(sys.modules.items()):
            if module is None or not name.startswith("tools.hermes_core"):
                continue
            for attribute, value in tuple(vars(module).items()):
                if isinstance(value, str) and value == old:
                    monkeypatch.setattr(module, attribute, new)

    replace_aliases(old_transport, candidate_transport)
    replace_aliases(old_path, CANDIDATE_PATH)
    replace_aliases(old_hash, CANDIDATE_HASH)
    replace_aliases(old_version, "7.6.2")
    for name, module in tuple(sys.modules.items()):
        if module is None or not name.startswith("tools.hermes_core"):
            continue
        receivers = getattr(module, "QUALIFIED_RECEIVERS", None)
        if isinstance(receivers, dict) and "kilo-cli-agent" in receivers:
            monkeypatch.setitem(receivers["kilo-cli-agent"], "transport_contract_id", candidate_transport)

    # These three cached identities break circular imports in the current chain.
    for key, attribute in (
        ("EA-4E.17", "CURRENT_EA4E17_ISSUANCE_CONTRACT_ID"),
        ("EA-4E.21", "CURRENT_EA4E21_BINDING_CONTRACT_ID"),
        ("EA-4E.22", "CURRENT_EA4E22_INTEGRATION_CONTRACT_ID"),
    ):
        monkeypatch.setattr(binding, attribute, current_ids()[key])

    new_ids = current_ids()
    assert candidate_transport == "3c54405378c314e52afc95fbe055fd0a4249f0d78a515a108126b8e4fd73363e"
    assert new_ids == EXPECTED_IDS
    assert current_ids() == new_ids
    assert set(new_ids) == set(old_ids)
    assert all(new_ids[key] != old_ids[key] for key in old_ids)
    successor_material = binding.kilo_executable_successor_binding_material()
    successor_material["predecessor_executable_version"] = old_version
    successor_material["predecessor_transport_contract_id"] = old_transport
    new_binding = sha256_payload(successor_material)
    assert new_binding == "b89f9f02f3e99cf70a98de8b4fb02b545e51855bb7340ed829ece749256b9be1"
    assert new_binding != binding.KILO_EXECUTABLE_SUCCESSOR_BINDING_ID
    print(json.dumps({"candidate_transport": candidate_transport,
                      "candidate_executable_binding": new_binding,
                      "predecessor_version": old_version,
                      "old_contract_ids": old_ids, "candidate_contract_ids": new_ids}, sort_keys=True))
