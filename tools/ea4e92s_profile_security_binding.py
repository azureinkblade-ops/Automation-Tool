"""Bind reviewed profile identity to SID-backed creation attributes; fake-only."""

import ctypes

from dataclasses import dataclass

from tools.ea4e92s_profile_preflight import review_existing_profile
from tools.ea4e92s_sid_ownership import prepare_reviewed_security


class UnknownBoundCleanup(RuntimeError):
    def __init__(self, message, bound):
        super().__init__(message)
        self.bound = bound


@dataclass
class BoundProfileSecurity:
    profile: object
    security: object
    state: str = "owned"

    def close(self):
        if self.state == "closed":
            return
        if self.state != "owned":
            raise UnknownBoundCleanup(
                "profile-bound cleanup requires reconciliation", self)
        self.state = "unknown"
        try:
            self.security.close()
        except BaseException as error:
            raise UnknownBoundCleanup(
                "profile-bound cleanup requires reconciliation", self) from error
        self.state = "closed"


def prepare_profile_bound_security(profile_api, sid_api, attribute_api, job_handle,
                                   profile_name, expected_sid, expected_storage_path,
                                   expected_volume_serial, expected_file_id):
    """Review profile first, then derive its SID and retain both through cleanup.

    This orders value-level collaborators only. It does not make inspection
    race-free or prove ACLs, token identity, native containment, or launch safety.
    """
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if type(job_handle) is not int or not 0 < job_handle <= pointer_max:
        raise ValueError("valid job handle required")
    profile = review_existing_profile(
        profile_api, profile_name, expected_sid, expected_storage_path,
        expected_volume_serial, expected_file_id)
    security = prepare_reviewed_security(
        sid_api, attribute_api, job_handle, profile.profile_name, profile.sid)
    return BoundProfileSecurity(profile, security)
