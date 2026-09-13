"""Canonical Kilo 7.6.2 successor identity and historical EA-4E IDs.

This module is data and hashing only. It has no process-launch capability.
"""
from __future__ import annotations

from typing import Any

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.kilo_adapter import (
    KILO_TRANSPORT_CONTRACT_ID,
    PINNED_KILO_PATH,
    PINNED_KILO_SHA256,
    PINNED_KILO_VERSION,
    _canonical_material,
)


KILO_RECEIVER_ID = "kilo-cli-agent"
KILO_MODEL_BINDING_ID = "b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544"

HISTORICAL_KILO_7_5_16_PATH = r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.16-win32-x64\bin\kilo.exe"
HISTORICAL_KILO_7_5_16_SHA256 = "8ddb47c7ae088c9f2118cec8824d618eea498b3d580970a5f094c7390633a851"
HISTORICAL_KILO_7_5_16_TRANSPORT_CONTRACT_ID = "52c828de66703a5ea587e51940dca0ec5c13a92af72b1836e6fc0225a83a5b63"
HISTORICAL_KILO_7_5_16_EXECUTABLE_BINDING_ID = "f681bc8bbfaeca4b3a1199254583f34327ac0de5e12a3ccbc0ff33411eb96563"

HISTORICAL_EA4E_7_5_16_CONTRACT_IDS = {
    "EA-4E.6": "a80122e6363f67148f9737f096057f2874aa594f04ddb2d18ddab3598fa94c49",
    "EA-4E.7": "05cad9f532b0bc37a5fa28104f72b14a08b53d050c37912f6e367edb22cadfe4",
    "EA-4E.8": "57b48875a3d446e4c2a417975c235c7360d4be6c96b4f0e380965553a126402d",
    "EA-4E.11": "578e0790c6317298d7c81ab5b0ed58e46a197aecdece050ed59c18d9ef29d2d0",
    "EA-4E.14": "ef709f6c2678027f694c3c9a55a498ec973977868428116bfa8b9476118f7f52",
    "EA-4E.17": "62ba7ba5689ff467b8609f924abdf6f1d478a037214dd99c4cbdcccbf6dfbd5b",
    "EA-4E.18": "921ea6c7ce32e57880bd67116e18f943faa66d265f685a9b59d632123c371cb3",
    "EA-4E.21": "eac6a628e11d3d7235e09a2bf745bc2efda9856baf47c432b7ad4813a36691de",
    "EA-4E.22": "93b284477a6f760170058a6ed026592d2238f0a1da7b5905eab8f70c6316eefe",
    "EA-4E.23": "b918118df4b7d72ab632737ce75ca700426e40932cd21a83ead15b3d20ee2319",
    "EA-4E.26": "05880849e3972a5553c2ea7b9ed7e75df33bc8ca3f990df9bf65bc9b15da9891",
    "EA-4E.28": "4b1953dbdf28753a940bb6fed41ea38efd7ed92d657e9d3cdca4b1b760105c88",
    "EA-4E.29": "ac2c38e726a2469b80590f6976acad9a5141e0efb26c2726e342420118ef21f1",
}

HISTORICAL_KILO_7_5_15_PATH = (
    r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.15-win32-x64\bin\kilo.exe"
)
HISTORICAL_KILO_7_5_15_SHA256 = (
    "78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25"
)
HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID = (
    "d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd"
)
HISTORICAL_KILO_7_5_15_EXECUTABLE_BINDING_ID = (
    "01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982"
)

HISTORICAL_KILO_7_5_9_PATH = (
    r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.9-win32-x64\bin\kilo.exe"
)
HISTORICAL_KILO_7_5_9_SHA256 = (
    "ec8737555947a145f3418962890f539b6b175ba3de125689f7ccb197d0004a36"
)
HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID = (
    "c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500"
)

HISTORICAL_EA4E_CONTRACT_IDS: dict[str, str] = {
    "EA-4E.6": "92b4a457bcfbe70fb993d44ba3f087c33f2804820398e107d44af6a90fdd0e9f",
    "EA-4E.7": "c21e17d125b5cb9292a5cb639e3b9b31af8e52b2577d700eb6307881aeeb2048",
    "EA-4E.8": "6ac0a3cdb3013d26244fed6998f4a3b0107ce1395f99a7c9acd9aa8df0f6922d",
    "EA-4E.11": "0d0b2d0327c5f3c4f32d47563f86fe2158b9b31a530ccbb26568f960c73df9c6",
    "EA-4E.14": "89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6",
    "EA-4E.17": "26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78",
    "EA-4E.18": "d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459",
    "EA-4E.21": "99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7",
    "EA-4E.22": "e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a",
    "EA-4E.23": "e638e8ff695172eceaf5c36baa1f5063633b32e344971a7d6fc54cf456faff91",
    "EA-4E.26": "84aad8495a6ec034c763f8c62a98ec41e85ef48c2b453bd098bc3cf57f624a67",
    "EA-4E.28": "395944480c5ea2cde374b07093f07b6e44633f404abb8e420136ee5516b910e1",
    "EA-4E.29": "821941da6ea4b08105c359afeb86193e343a429b0a74a32826bd6370faaa5166",
}

HISTORICAL_EA4E_7_5_15_CONTRACT_IDS: dict[str, str] = {
    "EA-4E.6": "292f7deeb479cd45c6f33f3466305e7f225c05d9f48f9eeb8dc13f944d7162a1",
    "EA-4E.7": "6de9f8b959db33bd2c2885396507baed47a3eadf07423c0e545afe4cc3274661",
    "EA-4E.8": "9785647334992c514ef56013c2e410be48c42a3c1813b377e601823387be67a2",
    "EA-4E.11": "af7d731ff21614f3ab0e92beb8927d3063e06707af7a9a89bc3d3b7c91e7927a",
    "EA-4E.14": "b057272ee70a4f5fceb9500ccf699097ed2de2edfc21e8f47fe3f9247e52f20b",
    "EA-4E.17": "5082b1a227a53cfe711bcf3c5d2193cd47031d75d7ec7650d8ab4c2389194e93",
    "EA-4E.18": "56471e6509ccc2e99a7c609354748c51a0ada18bda8b92648c21bec584c1ceb3",
    "EA-4E.21": "a25a6ba03b6a44f35511bec4b89c332043cd252ea3d1e185bd1b0a5c966fee33",
    "EA-4E.22": "0e9d206a0b5d78592bafad624421439774e6c7ffe34a7c9d4c41a66aeb0504bd",
    "EA-4E.23": "7bc3d2e036beacaef5aaabd054730dfbd49c57a0c36bbaab6f56894798be4687",
    "EA-4E.26": "52edc7ad0be1bf446034ad31189a9172a6a35c98c8619b113f4a836320b8887e",
    "EA-4E.28": "90c96695f6294bed90eed1b630b1b44f7faca859b6b818ea2a744c1b753eb5b1",
    "EA-4E.29": "2d2e42ebbaaa1eacabfbd9a09cf3a542f0424b26c96fb4e6b0a7984245039d87",
}

# Current dependency IDs that EA-4E.23 cannot import from their defining
# modules without creating a circular import. These are recomputed and
# regression-checked from the current source during the successor roll.
CURRENT_EA4E17_ISSUANCE_CONTRACT_ID = (
    "30c35204bb118b8978e6171ebef11e54fa90c6497c27da786717836af17b62ba"
)
CURRENT_EA4E21_BINDING_CONTRACT_ID = (
    "2dabd852fd943cb13f23986621aac4d59f4b0054a353808ec155e0ff1b24dc5a"
)
CURRENT_EA4E22_INTEGRATION_CONTRACT_ID = (
    "8aa6bb3760258d14de1621912072c0374ada91d444f6f51d03648ff4a8e51a3c"
)


def kilo_executable_successor_binding_material() -> dict[str, Any]:
    """Return the canonical installed-executable successor binding."""
    return {
        "schema_id": "hermes.kilo-executable-successor-binding/v1",
        "artifact_version": "1",
        "receiver_id": KILO_RECEIVER_ID,
        "executable_version": PINNED_KILO_VERSION,
        "executable_path": PINNED_KILO_PATH,
        "executable_sha256": PINNED_KILO_SHA256,
        "transport_contract_id": KILO_TRANSPORT_CONTRACT_ID,
        "model_binding_id": KILO_MODEL_BINDING_ID,
        "predecessor_executable_version": "7.5.16",
        "predecessor_transport_contract_id": HISTORICAL_KILO_7_5_16_TRANSPORT_CONTRACT_ID,
        "automatic_substitution": False,
    }


def compute_kilo_executable_successor_binding_id() -> str:
    return sha256_payload(kilo_executable_successor_binding_material())


def verify_kilo_executable_successor_binding(material: dict[str, Any]) -> bool:
    """Fail closed unless every canonical successor field matches exactly."""
    return material == kilo_executable_successor_binding_material()


def historical_kilo_7_5_9_transport_material() -> dict[str, Any]:
    """Reconstruct the predecessor material without making it selectable."""
    return _canonical_material(
        HISTORICAL_KILO_7_5_9_SHA256,
        "7.5.9",
        binary_path=HISTORICAL_KILO_7_5_9_PATH,
        source_commit="fa02955bfa17b60e57e0d7406d200a73337472ee",
        source_tag="v7.5.6",
    )


def compute_historical_kilo_7_5_9_transport_contract_id() -> str:
    return sha256_payload(historical_kilo_7_5_9_transport_material())


KILO_EXECUTABLE_SUCCESSOR_BINDING_ID = compute_kilo_executable_successor_binding_id()
