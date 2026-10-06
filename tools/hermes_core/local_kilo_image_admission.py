"""Non-live metadata admission for the provisional Kilo Linux image."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA_ID = "hermes.local-kilo-image-admission/v1"
IMAGE_ID = "sha256:2eaab2a5675726461630106859873c29f03641c142ae47c6b6060aebc611504d"
IMAGE_INDEX_ID = "sha256:c170379623cd8d16feb2c15fcdd473c401275336dc046fe72a5a5075c3474303"
IMAGE_OS = "linux"
IMAGE_ARCH = "amd64"
IMAGE_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
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

    descriptor = metadata.get("Descriptor")
    if not isinstance(descriptor, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_IMAGE_DESCRIPTOR")
    if descriptor.get("digest") != IMAGE_ID or descriptor.get("mediaType") != IMAGE_MEDIA_TYPE:
        return ImageAdmissionResult("DENY", "IMAGE_DESCRIPTOR_MISMATCH")
    if descriptor.get("platform") != {"os": IMAGE_OS, "architecture": IMAGE_ARCH}:
        return ImageAdmissionResult("DENY", "IMAGE_DESCRIPTOR_PLATFORM_MISMATCH")

    if config.get("User") != IMAGE_USER:
        return ImageAdmissionResult("DENY", "IMAGE_USER_MISMATCH")
    if config.get("Entrypoint") != list(IMAGE_ENTRYPOINT):
        return ImageAdmissionResult("DENY", "IMAGE_ENTRYPOINT_MISMATCH")
    if config.get("WorkingDir") != IMAGE_WORKDIR:
        return ImageAdmissionResult("DENY", "IMAGE_WORKDIR_MISMATCH")
    return ImageAdmissionResult("MATCH", "IMAGE_METADATA_MATCHED")


def inspect_prestart_image_binding(
    container: Mapping[str, Any] | None,
    image: Mapping[str, Any] | None,
) -> ImageAdmissionResult:
    """Bind a created container's local index to the inspected amd64 manifest."""
    image_result = inspect_provisional_kilo_image(image)
    if image_result.decision != "MATCH":
        return ImageAdmissionResult("DENY", image_result.reason)
    if not isinstance(image, Mapping) or not isinstance(container, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_CONTAINER_METADATA")
    repo_digests = image.get("RepoDigests")
    if not isinstance(repo_digests, list) or f"hermes/kilo@{IMAGE_INDEX_ID}" not in repo_digests:
        return ImageAdmissionResult("DENY", "IMAGE_INDEX_REFERENCE_MISMATCH")
    state = container.get("State")
    if not isinstance(state, Mapping) or state.get("Status") != "created":
        return ImageAdmissionResult("DENY", "CONTAINER_NOT_PRESTART")
    if container.get("Image") != IMAGE_INDEX_ID:
        return ImageAdmissionResult("DENY", "CONTAINER_IMAGE_INDEX_MISMATCH")
    return ImageAdmissionResult("MATCH", "PRESTART_IMAGE_BOUND")
