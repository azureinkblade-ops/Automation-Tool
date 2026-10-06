"""Non-live metadata admission for the provisional Kilo Linux image."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA_ID = "hermes.local-kilo-image-admission/v1"
IMAGE_ID = "sha256:cf003ba6e84cfd0fa8c2951dfe44454e25f9cf5e42eb6bf3ba82349b26b99120"
IMAGE_OS = "linux"
IMAGE_ARCH = "amd64"
IMAGE_USER = "65532:65532"
IMAGE_ENTRYPOINT = ("/opt/kilo/kilo",)
IMAGE_WORKDIR = "/work"


@dataclass(frozen=True)
class ImageAdmissionResult:
    decision: str
    reason: str
    receiver_executed: bool = False
    provenance_checked: bool = False


def inspect_provisional_kilo_image(metadata: Mapping[str, Any] | None) -> ImageAdmissionResult:
    """Match daemon-reported image metadata; never authorize a launch."""
    if not isinstance(metadata, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_IMAGE_METADATA")
    config = metadata.get("Config")
    if not isinstance(config, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_IMAGE_CONFIG")

    expected = {
        "Id": IMAGE_ID,
        "Os": IMAGE_OS,
        "Architecture": IMAGE_ARCH,
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            return ImageAdmissionResult("DENY", f"IMAGE_{field.upper()}_MISMATCH")

    if config.get("User") != IMAGE_USER:
        return ImageAdmissionResult("DENY", "IMAGE_USER_MISMATCH")
    if config.get("Entrypoint") != list(IMAGE_ENTRYPOINT):
        return ImageAdmissionResult("DENY", "IMAGE_ENTRYPOINT_MISMATCH")
    if config.get("WorkingDir") != IMAGE_WORKDIR:
        return ImageAdmissionResult("DENY", "IMAGE_WORKDIR_MISMATCH")
    return ImageAdmissionResult("MATCH", "IMAGE_METADATA_MATCHED")
