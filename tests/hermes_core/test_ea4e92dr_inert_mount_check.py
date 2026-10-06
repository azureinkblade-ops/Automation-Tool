"""Fake-only prestart mount checks; no Docker or receiver process."""

from copy import deepcopy
import inspect

import pytest

from tools.hermes_core import local_kilo_image_admission as image_subject
from tools.hermes_core import local_kilo_inert_mount_check as subject


INPUT = r"C:\temp\ea4e-probe\input"
RUNTIME = r"C:\temp\ea4e-probe\runtime"


def metadata():
    image = {
        "Id": image_subject.IMAGE_ID,
        "Os": "linux",
        "Architecture": "amd64",
        "Descriptor": {
            "digest": image_subject.IMAGE_ID,
            "mediaType": image_subject.IMAGE_MEDIA_TYPE,
            "platform": {"os": "linux", "architecture": "amd64"},
        },
        "Config": {
            "User": "65532:65532",
            "Entrypoint": ["/opt/kilo/kilo"],
            "WorkingDir": "/work",
        },
        "RepoDigests": [f"hermes/kilo@{image_subject.IMAGE_INDEX_ID}"],
    }
    container = {
        "Image": image_subject.IMAGE_INDEX_ID,
        "State": {"Status": "created"},
        "Config": {
            "Entrypoint": ["/bin/sh"],
            "Cmd": ["-ec", subject.PROBE_COMMAND],
            "User": "65532:65532",
            "WorkingDir": "/work",
            "Env": [],
        },
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "PidsLimit": 32,
            "Memory": 67108864,
            "NanoCpus": 250000000,
            "CapAdd": None,
            "Devices": [],
            "Binds": None,
            "PidMode": "",
            "IpcMode": "private",
        },
        "Mounts": [
            {"Type": "bind", "Source": INPUT, "Destination": "/reviewed-input", "RW": False},
            {"Type": "bind", "Source": RUNTIME, "Destination": "/tmp/kilo-home", "RW": True},
        ],
    }
    return container, image


def check(container, image):
    return subject.inspect_inert_mount_probe(container, image, INPUT, RUNTIME)


def test_exact_fake_metadata_matches_without_authorizing_execution():
    result = check(*metadata())
    assert result.decision == "MATCH"
    assert result.receiver_executed is False
    assert result.provenance_checked is False


@pytest.mark.parametrize("mutate", [
    lambda c: c["Config"].update(Cmd=["-ec", "id"]),
    lambda c: c["Config"].update(Entrypoint=["/opt/kilo/kilo"]),
    lambda c: c["Config"].update(User="0:0"),
    lambda c: c["Config"].update(Env=["TOKEN=secret"]),
    lambda c: c["HostConfig"].update(NetworkMode="bridge"),
    lambda c: c["HostConfig"].update(ReadonlyRootfs=False),
    lambda c: c["HostConfig"].update(Privileged=True),
    lambda c: c["HostConfig"].update(CapAdd=["SYS_ADMIN"]),
    lambda c: c["HostConfig"].update(Binds=["C:\\:/host"]),
    lambda c: c["HostConfig"].update(PidMode="host"),
    lambda c: c["HostConfig"].update(PidsLimit=0),
    lambda c: c["HostConfig"].update(PortBindings={"80/tcp": [{"HostPort": "80"}]}),
    lambda c: c["Mounts"].append({"Type": "bind", "Source": "C:/secret", "Destination": "/secret", "RW": True}),
    lambda c: c["Mounts"][0].update(RW=True),
    lambda c: c["Mounts"][1].update(Source=INPUT),
    lambda c: c["Mounts"][1].update(Type="volume"),
    lambda c: c["State"].update(Status="running"),
])
def test_unexpected_prestart_metadata_denied(mutate):
    container, image = deepcopy(metadata())
    mutate(container)
    assert check(container, image).decision == "DENY"


def test_image_mismatch_denied():
    container, image = metadata()
    image["Id"] = "sha256:" + "0" * 64
    assert check(container, image).decision == "DENY"


def test_source_identity_required():
    container, image = metadata()
    assert subject.inspect_inert_mount_probe(container, image, INPUT, INPUT).decision == "DENY"


def test_no_runtime_capability_in_checker():
    source = inspect.getsource(subject).lower()
    for forbidden in ("subprocess", "requests", "socket", "popen", "exec("):
        assert forbidden not in source
