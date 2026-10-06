"""Fake-only image metadata checks. No Docker, receiver, or model call."""

from copy import deepcopy
import inspect

import pytest

from tools.hermes_core import local_kilo_image_admission as subject


def metadata():
    return {
        "Id": subject.IMAGE_ID,
        "Os": "linux",
        "Architecture": "amd64",
        "Descriptor": {
            "digest": subject.IMAGE_ID,
            "mediaType": subject.IMAGE_MEDIA_TYPE,
            "platform": {"os": "linux", "architecture": "amd64"},
        },
        "Config": {
            "User": "65532:65532",
            "Entrypoint": ["/opt/kilo/kilo"],
            "WorkingDir": "/work",
        },
    }


def test_matching_metadata_is_not_execution_or_provenance():
    result = subject.inspect_provisional_kilo_image(metadata())
    assert result.decision == "MATCH"
    assert result.reason == "IMAGE_METADATA_MATCHED"
    assert result.receiver_executed is False
    assert result.provenance_checked is False


@pytest.mark.parametrize("field,bad", [
    ("Id", "sha256:" + "0" * 64),
    ("Id", "sha256:c170379623cd8d16feb2c15fcdd473c401275336dc046fe72a5a5075c3474303"),
    ("Id", "hermes/kilo:7.8.3-linux-amd64-provisional"),
    ("Os", "windows"),
    ("Architecture", "arm64"),
])
def test_wrong_image_identity_denied(field, bad):
    observed = metadata()
    observed[field] = bad
    assert subject.inspect_provisional_kilo_image(observed).decision == "DENY"


@pytest.mark.parametrize("field,bad", [
    ("User", "root"),
    ("Entrypoint", ["/bin/sh"]),
    ("Entrypoint", ["/opt/kilo/kilo", "--auto"]),
    ("WorkingDir", "/"),
])
def test_wrong_image_configuration_denied(field, bad):
    observed = metadata()
    observed["Config"][field] = bad
    assert subject.inspect_provisional_kilo_image(observed).decision == "DENY"


@pytest.mark.parametrize("bad", [None, {}, {"Config": None}, {"Config": []}])
def test_incomplete_metadata_denied(bad):
    assert subject.inspect_provisional_kilo_image(bad).decision == "DENY"


@pytest.mark.parametrize("descriptor", [
    None,
    {},
    {"digest": "sha256:" + "0" * 64, "mediaType": subject.IMAGE_MEDIA_TYPE,
     "platform": {"os": "linux", "architecture": "amd64"}},
    {"digest": subject.IMAGE_ID, "mediaType": "application/vnd.oci.image.index.v1+json",
     "platform": {"os": "linux", "architecture": "amd64"}},
    {"digest": subject.IMAGE_ID, "mediaType": subject.IMAGE_MEDIA_TYPE,
     "platform": {"os": "linux", "architecture": "arm64"}},
])
def test_missing_or_wrong_manifest_descriptor_denied(descriptor):
    observed = metadata()
    observed["Descriptor"] = descriptor
    assert subject.inspect_provisional_kilo_image(observed).decision == "DENY"


def test_caller_mutation_cannot_change_expected_identity():
    observed = deepcopy(metadata())
    subject.inspect_provisional_kilo_image(observed)
    observed["Config"]["Entrypoint"].append("--auto")
    assert subject.inspect_provisional_kilo_image(observed).decision == "DENY"


def test_module_contains_no_runtime_capability():
    source = inspect.getsource(subject)
    for forbidden in ("subprocess", "docker", "requests", "socket", "popen", "exec("):
        assert forbidden not in source.lower()
