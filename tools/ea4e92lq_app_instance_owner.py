"""In-memory ownership of one launcher-created app instance; no native launcher."""

from dataclasses import dataclass
import re
import sys
import uuid

from tools.ea4e92s_retained_snapshot_provider import ProcessQuery


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_HANDLE = (2 * sys.maxsize) + 1


class AppInstanceDenied(RuntimeError):
    """The expected live app instance is not established."""


class AppInstanceUnknown(AppInstanceDenied):
    """An external launch or observation outcome needs reconciliation."""


@dataclass(frozen=True)
class AppLaunchReceipt:
    launcher_instance_id: str
    app_instance_nonce: str
    package_sha256: str
    process_handle: int
    process_id: int
    process_creation_time_100ns: int


@dataclass(frozen=True)
class AppProcessObservation:
    process_handle: int
    process_id: int
    app_instance_nonce: str
    package_sha256: str
    alive: bool
    process_creation_time_100ns: int


def _uuid(value):
    if type(value) is not str:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _positive(value, maximum):
    return type(value) is int and 0 < value <= maximum


class AppInstanceOwner:
    """Retain one collaborator-returned receipt and deny ambiguous transitions.

    The collaborator must be an independently trusted native launcher before
    this state machine can contribute to any production authority decision.
    """

    def __init__(self, launcher, *, launcher_instance_id, package_sha256,
                 process_api=None):
        if not _uuid(launcher_instance_id):
            raise AppInstanceDenied("launcher identity malformed")
        if type(package_sha256) is not str or not _SHA256.fullmatch(package_sha256):
            raise AppInstanceDenied("package identity malformed")
        self._launcher = launcher
        self._process_api = process_api
        self.launcher_instance_id = launcher_instance_id
        self.package_sha256 = package_sha256
        self.state = "NEW"
        self._receipt = None

    def start(self):
        if self.state != "NEW":
            raise AppInstanceDenied("app launch cannot replay")
        self.state = "UNKNOWN"
        try:
            receipt = self._launcher.launch(
                launcher_instance_id=self.launcher_instance_id,
                package_sha256=self.package_sha256,
            )
        except BaseException as error:
            raise AppInstanceUnknown("app launch outcome unknown") from error
        if (type(receipt) is not AppLaunchReceipt
                or receipt.launcher_instance_id != self.launcher_instance_id
                or receipt.package_sha256 != self.package_sha256
                or not _uuid(receipt.app_instance_nonce)
                or receipt.app_instance_nonce == self.launcher_instance_id
                or not _positive(receipt.process_handle, _MAX_HANDLE)
                or not _positive(receipt.process_id, 0xFFFFFFFF)
                or not _positive(receipt.process_creation_time_100ns,
                                 0xFFFFFFFFFFFFFFFF)):
            raise AppInstanceUnknown("launcher receipt is not canonical")
        self._receipt = receipt
        self.state = "OWNED"

    def resolve_live(self):
        if self.state != "OWNED" or self._receipt is None:
            raise AppInstanceDenied("app instance is not owned")
        receipt = self._receipt
        try:
            if self._process_api is None:
                observation = self._launcher.observe(receipt.process_handle)
            else:
                process = self._process_api.query_process(receipt.process_handle)
                if (type(process) is not ProcessQuery
                        or type(process.process_id) is not int
                        or type(process.creation_time_100ns) is not int
                        or type(process.present) is not bool):
                    raise ValueError("kernel process observation malformed")
                observation = AppProcessObservation(
                    receipt.process_handle, process.process_id,
                    receipt.app_instance_nonce, receipt.package_sha256,
                    process.present, process.creation_time_100ns)
        except BaseException as error:
            self.state = "UNKNOWN"
            raise AppInstanceUnknown("app observation outcome unknown") from error
        if (type(observation) is not AppProcessObservation
                or type(observation.alive) is not bool
                or observation.process_handle != receipt.process_handle
                or observation.process_id != receipt.process_id
                or observation.app_instance_nonce != receipt.app_instance_nonce
                or observation.package_sha256 != receipt.package_sha256
                or observation.process_creation_time_100ns
                != receipt.process_creation_time_100ns):
            self.state = "UNKNOWN"
            raise AppInstanceUnknown("app process identity drifted")
        if observation.alive is False:
            self.state = "EXITED"
            raise AppInstanceDenied("app process exited")
        return receipt

    def close_exited(self):
        if self.state != "EXITED" or self._receipt is None:
            raise AppInstanceDenied("exited handle is not available for close")
        self.state = "UNKNOWN"
        try:
            if self._process_api is None:
                closed = self._launcher.close_process_handle(
                    self._receipt.process_handle)
            else:
                closed = self._process_api.close_process(
                    self._receipt.process_handle)
        except BaseException as error:
            raise AppInstanceUnknown("app handle close outcome unknown") from error
        if closed is not True:
            raise AppInstanceUnknown("app handle close unconfirmed")
        self.state = "CLOSED"
