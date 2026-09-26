"""Pure command-line quoting and retained value buffers; no launch API."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_launch_inputs import build_probe_launch_inputs
from tools.ea4e92s_startupinfo_abi import prepare_startup_info_ex


def encode_windows_argv(argv):
    """Encode argv using the Windows C runtime backslash/quote rules."""
    if type(argv) is not tuple or not argv:
        raise ValueError("nonempty argv tuple required")
    encoded = []
    for argument in argv:
        if type(argument) is not str or "\0" in argument:
            raise ValueError("argv entry malformed")
        quoted = not argument or " " in argument or "\t" in argument
        pieces = ['"'] if quoted else []
        slashes = 0
        for character in argument:
            if character == "\\":
                slashes += 1
            elif character == '"':
                pieces.append("\\" * (2 * slashes + 1))
                pieces.append('"')
                slashes = 0
            else:
                pieces.append("\\" * slashes)
                pieces.append(character)
                slashes = 0
        pieces.append("\\" * (2 * slashes if quoted else slashes))
        if quoted:
            pieces.append('"')
        encoded.append("".join(pieces))
    command_line = " ".join(encoded)
    try:
        units = len(command_line.encode("utf-16-le")) // 2 + 1
    except UnicodeEncodeError as error:
        raise ValueError("argv Unicode invalid") from error
    if units > 32767:
        raise ValueError("command line exceeds Windows limit")
    return command_line


@dataclass(frozen=True)
class PreparedProbeBuffers:
    inputs: object
    startup: object
    request_root: object
    application_name: ctypes.Array
    command_line: ctypes.Array
    environment: ctypes.Array
    current_directory: ctypes.Array
    startup_snapshot: bytes
    attributes_snapshot: bytes


def prepare_probe_buffers(reviewed, candidate, attributes, *, runtime_bytes,
                          bootstrap_bytes, request_bytes):
    """Own exact synthetic buffers; native path and identity checks are later."""
    if ctypes.sizeof(ctypes.c_wchar) != 2:
        raise ValueError("Windows UTF-16 wchar required")
    inputs = build_probe_launch_inputs(
        reviewed, candidate, runtime_bytes=runtime_bytes,
        bootstrap_bytes=bootstrap_bytes, request_bytes=request_bytes)
    startup = prepare_startup_info_ex(attributes)
    command_line = encode_windows_argv(inputs.argv)
    try:
        reviewed.request_root.path.encode("utf-16-le")
    except UnicodeEncodeError as error:
        raise ValueError("working directory Unicode invalid") from error
    value = PreparedProbeBuffers(
        inputs,
        startup,
        reviewed.request_root,
        ctypes.create_unicode_buffer(inputs.application_name),
        ctypes.create_unicode_buffer(command_line),
        ctypes.create_string_buffer(inputs.environment_block,
                                    len(inputs.environment_block)),
        ctypes.create_unicode_buffer(reviewed.request_root.path),
        ctypes.string_at(ctypes.addressof(startup.value),
                         ctypes.sizeof(startup.value)),
        bytes(attributes.handle.buffer),
    )
    validate_prepared_probe_buffers(value)
    return value


def validate_prepared_probe_buffers(value):
    """Detect in-memory drift; this is not a native readiness verdict."""
    if type(value) is not PreparedProbeBuffers:
        raise ValueError("exact prepared buffer owner required")
    try:
        current = prepare_startup_info_ex(value.startup.attributes)
        attributes = value.startup.attributes
        if (value.startup.value.lpAttributeList != current.value.lpAttributeList
                or value.application_name.value != value.inputs.application_name
                or value.command_line.value != encode_windows_argv(value.inputs.argv)
                or bytes(value.environment) != value.inputs.environment_block
                or value.current_directory.value != value.request_root.path
                or ctypes.string_at(ctypes.addressof(value.startup.value),
                                    ctypes.sizeof(value.startup.value))
                != value.startup_snapshot
                or bytes(attributes.handle.buffer) != value.attributes_snapshot):
            raise ValueError("prepared buffer identity drift")
    except (AttributeError, TypeError) as error:
        raise ValueError("prepared buffer owner invalid") from error
    return value
