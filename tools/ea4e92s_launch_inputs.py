"""Value-only probe launch inputs; no command line or native process call."""

from dataclasses import dataclass

from tools.ea4e92s_creation_provenance import (
    CREATE_SUSPENDED,
    CREATE_UNICODE_ENVIRONMENT,
    EXTENDED_STARTUPINFO_PRESENT,
)
from tools.ea4e92s_probe_admission import validate_probe_admission


@dataclass(frozen=True)
class ProbeLaunchInputs:
    application_name: str
    argv: tuple
    environment_block: bytes
    creation_flags: int
    admission: object


def build_probe_launch_inputs(reviewed, candidate, *, runtime_bytes,
                              bootstrap_bytes, request_bytes):
    """Re-admit exact content and retain immutable inputs for later review."""
    admission = validate_probe_admission(
        reviewed, candidate,
        runtime_bytes=runtime_bytes,
        bootstrap_bytes=bootstrap_bytes,
        request_bytes=request_bytes,
    )
    entries = [f"{name}={value}" for name, value in reviewed.environment]
    environment_block = ("\0".join(entries) + "\0\0").encode("utf-16-le")
    return ProbeLaunchInputs(
        reviewed.runtime.path,
        reviewed.argv,
        environment_block,
        CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
        | EXTENDED_STARTUPINFO_PRESENT,
        admission,
    )
