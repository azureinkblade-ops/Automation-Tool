"""Test-owned suspended-process ownership; no native adapter or launcher."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_windows_attributes import NativeAttributeList, WindowsAttributeApi


class SuspendedProcessDenied(RuntimeError):
    """Creation was rejected after all returned handles were closed."""


class UnknownSuspendedProcess(RuntimeError):
    """Creation or cleanup outcome cannot be proven; automatic retry is barred."""

    def __init__(self, message, owned=None):
        super().__init__(message)
        self.owned = owned


@dataclass(frozen=True)
class SuspendedCreationResult:
    process_handle: int
    thread_handle: int
    process_id: int
    thread_id: int
    suspended: bool
    job_bound_at_creation: bool
    appcontainer_bound_at_creation: bool


@dataclass
class OwnedSuspendedProcess:
    api: object
    result: SuspendedCreationResult
    creation_owner: object
    state: str = "owned"

    def close(self):
        """Terminate the suspended child, then close thread and process handles."""
        if self.state == "closed":
            return
        if self.state != "owned":
            raise UnknownSuspendedProcess(
                "suspended-process cleanup requires reconciliation", self)

        self.state = "unknown"
        try:
            terminated = self.api.terminate(self.result.process_handle)
        except BaseException as error:
            raise UnknownSuspendedProcess(
                "suspended-process termination requires reconciliation", self) from error
        if terminated is not True:
            raise UnknownSuspendedProcess(
                "suspended-process termination requires reconciliation", self)

        confirmed = True
        operations = (
            ("close_thread", self.result.thread_handle),
            ("close_process", self.result.process_handle),
        )
        for operation_name, handle in operations:
            try:
                operation = getattr(self.api, operation_name)
                if operation(handle) is not True:
                    confirmed = False
            except BaseException:
                confirmed = False
        if not confirmed:
            raise UnknownSuspendedProcess(
                "suspended-process cleanup requires reconciliation", self)
        self.state = "closed"


def _valid_native_value(value, maximum):
    return type(value) is int and 0 < value <= maximum


def _owned_attribute_handle(creation_owner):
    security = getattr(creation_owner, "security", None)
    attributes = getattr(security, "attributes", None)
    if (getattr(creation_owner, "state", None) != "owned"
            or getattr(security, "state", None) != "owned"
            or getattr(attributes, "state", None) != "owned"):
        raise ValueError("owned creation attributes required")
    handle = getattr(attributes, "handle", None)
    if type(handle) is NativeAttributeList:
        keepalive = getattr(attributes, "keepalive", None)
        pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
        if (type(attributes.api) is not WindowsAttributeApi
                or handle.owner is not attributes.api
                or handle.closed or handle.failed
                or not isinstance(handle.buffer, ctypes.Array)
                or handle.keys != ["JOB_LIST", "SECURITY_CAPABILITIES"]
                or type(keepalive) is not tuple or len(keepalive) != 3
                or len(handle.values) != 2
                or handle.values[0] is not keepalive[0]
                or handle.values[1] is not keepalive[1]
                or keepalive[2] is not security
                or not isinstance(keepalive[0], ctypes.Array)
                or len(keepalive[0]) != 1
                or not _valid_native_value(keepalive[0][0], pointer_max)
                or not _valid_native_value(security.pointer, pointer_max)
                or keepalive[1].AppContainerSid != security.pointer):
            raise ValueError("reviewed native attribute list required")
        return handle.buffer
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if not _valid_native_value(handle, pointer_max):
        raise ValueError("valid attribute handle required")
    return handle


def create_owned_suspended_process(api, creation_owner):
    """Create through an injected collaborator and validate its exact result.

    ``creation_owner`` is borrowed and retained to preserve attribute lifetime;
    its caller remains responsible for closing it. No command, environment,
    native API, resume operation or fallback process path exists in this module.
    """
    attribute_handle = _owned_attribute_handle(creation_owner)
    try:
        created = api.create_suspended(attribute_handle)
    except BaseException as error:
        raise UnknownSuspendedProcess(
            "suspended-process creation outcome requires reconciliation") from error
    if type(created) is not SuspendedCreationResult:
        raise UnknownSuspendedProcess(
            "suspended-process creation returned noncanonical evidence")

    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    valid_handles = (
        _valid_native_value(created.process_handle, pointer_max)
        and _valid_native_value(created.thread_handle, pointer_max)
        and created.process_handle != created.thread_handle)
    if not valid_handles:
        raise UnknownSuspendedProcess(
            "suspended-process handle ownership is unknown")

    owned = OwnedSuspendedProcess(api, created, creation_owner)
    valid_ids = (
        _valid_native_value(created.process_id, 0xFFFFFFFF)
        and _valid_native_value(created.thread_id, 0xFFFFFFFF))
    proven_predicates = (
        created.suspended is True
        and created.job_bound_at_creation is True
        and created.appcontainer_bound_at_creation is True)
    if not valid_ids or not proven_predicates:
        try:
            owned.close()
        except UnknownSuspendedProcess:
            raise
        reason = "creation identity" if not valid_ids else "creation predicate"
        raise SuspendedProcessDenied(f"suspended-process {reason} not proven")
    return owned
