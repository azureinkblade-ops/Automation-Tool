"""Inert child-to-pipe-to-parser qualification without an issuer or agent."""

import base64
from dataclasses import replace
import subprocess

import pytest

from tools.ea4e92ne_app_challenge_frame import (
    AppChallengeExpectation,
    AppChallengeFrameDenied,
    encode_app_challenge_frame,
    parse_app_challenge_frame,
)
from tests.hermes_core.test_ea4e92ni_distinct_client_probe import executable


EXPECTED = AppChallengeExpectation(
    "718d4e99-9d30-42d1-a2ed-c3bf55734ac2",
    "621e57b3-ef5c-4fbe-8d0a-81f78d2c4ba3",
    "84bb0bea-ed17-4a29-a9ef-c2f76c8d16eb",
)


def _through_inert_pipe(executable, frame):
    result = subprocess.run(
        [str(executable), "WIRE", base64.b64encode(frame).decode("ascii")],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("WIRE_BASE64:")
    return base64.b64decode(result.stdout.strip().split(":", 1)[1], validate=True)


def test_canonical_challenge_survives_distinct_process_pipe(executable):
    frame = encode_app_challenge_frame(EXPECTED)
    captured = _through_inert_pipe(executable, frame)
    assert captured == frame
    parsed = parse_app_challenge_frame(captured, EXPECTED)
    assert parsed.app_instance_nonce == EXPECTED.app_instance_nonce


@pytest.mark.parametrize("frame", [
    b" " + encode_app_challenge_frame(EXPECTED),
    encode_app_challenge_frame(replace(
        EXPECTED, app_instance_nonce="00000000-ed17-4a29-a9ef-c2f76c8d16eb")),
])
def test_wire_capture_does_not_override_parser_denial(executable, frame):
    captured = _through_inert_pipe(executable, frame)
    assert captured == frame
    with pytest.raises(AppChallengeFrameDenied):
        parse_app_challenge_frame(captured, EXPECTED)
