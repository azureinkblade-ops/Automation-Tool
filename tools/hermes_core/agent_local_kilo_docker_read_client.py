"""Exact-ID Docker inspect transport contract; no command runner is wired."""

import hashlib
import json
import re
from pathlib import Path

from tools.hermes_core.delegated_task import DelegationIntegrityError


_ID = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_BYTES = 1024 * 1024
_TIMEOUT_SECONDS = 5


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _deny_constant(_value):
    raise ValueError("non-finite JSON value")


class AgentLocalKiloDockerReadClient:
    """Build pinned read-only CLI requests for an injected bounded runner."""

    def __init__(self, executable: str, executable_sha256: str, *, runner=None):
        if type(executable) is not str:
            raise DelegationIntegrityError("Docker read executable pin invalid")
        path = Path(executable)
        if (not path.is_absolute() or type(executable_sha256) is not str
                or not _ID.fullmatch(executable_sha256)):
            raise DelegationIntegrityError("Docker read executable pin invalid")
        self.executable = path
        self.executable_sha256 = executable_sha256
        self.runner = runner

    def _verify_executable(self):
        digest = hashlib.sha256()
        try:
            with self.executable.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise DelegationIntegrityError("Docker read executable unavailable") from exc
        if digest.hexdigest() != self.executable_sha256:
            raise DelegationIntegrityError("Docker read executable changed")

    def _inspect(self, kind: str, identity: str, expected_id: str | None = None):
        if self.runner is None:
            raise DelegationIntegrityError("Docker read runner disabled")
        if kind == "image":
            if type(identity) is not str or not _IMAGE.fullmatch(identity):
                raise DelegationIntegrityError("Docker read image identity denied")
            if type(expected_id) is not str or not _IMAGE.fullmatch(expected_id):
                raise DelegationIntegrityError("Docker read manifest identity denied")
            argv = (str(self.executable), "--context", "desktop-linux", "image",
                    "inspect", "--platform", "linux/amd64", identity)
        elif kind in ("container", "network"):
            if type(identity) is not str or not _ID.fullmatch(identity):
                raise DelegationIntegrityError("Docker read object identity denied")
            argv = (str(self.executable), "--context", "desktop-linux", kind,
                    "inspect", identity)
        else:
            raise DelegationIntegrityError("Docker read kind denied")
        self._verify_executable()
        if not callable(self.runner):
            raise DelegationIntegrityError("Docker read runner invalid")
        try:
            data = self.runner(
                argv, timeout_seconds=_TIMEOUT_SECONDS,
                max_output_bytes=_MAX_BYTES,
            )
        except Exception as exc:
            raise DelegationIntegrityError("Docker read command failed") from exc
        if type(data) is not bytes or not data or len(data) > _MAX_BYTES:
            raise DelegationIntegrityError("Docker read output bounds denied")
        try:
            value = json.loads(data.decode("utf-8", errors="strict"),
                               object_pairs_hook=_unique_object,
                               parse_constant=_deny_constant)
        except (UnicodeError, ValueError) as exc:
            raise DelegationIntegrityError("Docker read JSON denied") from exc
        if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
            raise DelegationIntegrityError("Docker read response shape denied")
        if kind == "image":
            if value[0].get("Id") != expected_id:
                raise DelegationIntegrityError("Docker read image mismatch")
        elif value[0].get("Id") != identity:
            raise DelegationIntegrityError("Docker read object mismatch")
        return value[0]

    def inspect_container(self, identity: str):
        return self._inspect("container", identity)

    def inspect_image(self, image_index: str, image_manifest: str):
        return self._inspect("image", image_index, image_manifest)

    def inspect_network(self, identity: str):
        return self._inspect("network", identity)
