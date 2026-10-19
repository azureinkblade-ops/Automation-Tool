"""Static descriptor screening; no pipe, token, issuer, or Docker action."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
APP = "S-1-5-21-1-2-3-1001"
BASE = ("O:BAG:BAD:P(A;;0x00000002;;;" + APP + ")"
        "(A;;GA;;;SY)(A;;GA;;;BA)S:(ML;;NW;;;ME)")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("descriptor-screen") / "screen.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPipeDescriptorScreen.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92nl_descriptor_screen.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def screen(executable, sddl, app=APP):
    result = subprocess.run(
        [str(executable), sddl, app], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def test_narrow_candidate_remains_static_only(executable):
    assert screen(executable, BASE) == "CANDIDATE:STATIC_ONLY"


@pytest.mark.parametrize("sddl, expected", [
    ("O:" + APP + "G:BAD:P(A;;0x2;;;" + APP + ")", "DENY:APP_OWNER_OR_OWNER_MISSING"),
    (BASE.replace("D:P", "D:"), "DENY:DACL_MISSING_OR_UNPROTECTED"),
    (BASE.replace("0x00000002", "GW"), "DENY:APP_GRANT_NOT_EXACT"),
    (BASE.replace("0x00000002", "0x00000006"), "DENY:APP_GRANT_NOT_EXACT"),
    (BASE.replace("0x00000002", "WD"), "DENY:APP_GRANT_NOT_EXACT"),
    (BASE.replace("0x00000002", "WO"), "DENY:APP_GRANT_NOT_EXACT"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;GA;;;WD)"), "DENY:BROAD_ALLOW"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;GA;;;AU)"), "DENY:BROAD_ALLOW"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;GA;;;BU)"), "DENY:BROAD_ALLOW"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;GA;;;IU)"), "DENY:BROAD_ALLOW"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;GA;;;CO)"), "DENY:BROAD_ALLOW"),
    (BASE.replace("(A;;GA;;;SY)", ""), "CANDIDATE:STATIC_ONLY"),
    (BASE.replace("(A;;0x00000002;;;" + APP + ")", ""), "DENY:APP_WRITE_MISSING"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;WD;;;S-1-5-21-1-2-3-2002)"),
     "DENY:UNTRUSTED_MUTATION_GRANT"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;WO;;;S-1-5-21-1-2-3-2002)"),
     "DENY:UNTRUSTED_MUTATION_GRANT"),
    (BASE.replace("(A;;GA;;;SY)", "(A;;0x00000004;;;S-1-5-21-1-2-3-2002)"),
     "DENY:UNTRUSTED_MUTATION_GRANT"),
    (BASE.replace("S:(ML", "(A;;0x00000002;;;" + APP + ")S:(ML"),
     "DENY:APP_GRANT_NOT_EXACT"),
    (BASE.replace("(A;;GA;;;SY)", "(A;CI;0x2;;;SY)"), "DENY:UNREVIEWED_ACE"),
])
def test_descriptor_cases(executable, sddl, expected):
    assert screen(executable, sddl) == expected


def test_invalid_inputs(executable):
    assert screen(executable, "not-sddl") == "DENY:INVALID_INPUT"
    assert screen(executable, BASE, "not-sid") == "DENY:INVALID_INPUT"


@pytest.mark.parametrize("sddl", [
    BASE.replace("S:(ML;;NW;;;ME)", ""),
    BASE.replace("S:(ML;;NW;;;ME)", "S:(ML;;NW;;;HI)"),
    BASE.replace("S:(ML;;NW;;;ME)", "S:(ML;;NW;;;LW)"),
    BASE.replace("S:(ML;;NW;;;ME)", "S:(ML;;NR;;;ME)"),
    BASE.replace("S:(ML;;NW;;;ME)", "S:(ML;;NW;;;ME)(ML;;NW;;;ME)"),
])
def test_missing_or_changed_mandatory_label_denied(executable, sddl):
    assert screen(executable, sddl) == "DENY:LABEL_MISSING_OR_UNREVIEWED"


@pytest.mark.parametrize("app", ["WD", "AU", "BU", "IU", "CO", "SY", "BA"])
def test_broad_or_privileged_identity_cannot_be_app(executable, app):
    sid = {"WD": "S-1-1-0", "AU": "S-1-5-11", "BU": "S-1-5-32-545",
           "IU": "S-1-5-4", "CO": "S-1-3-0", "SY": "S-1-5-18",
           "BA": "S-1-5-32-544"}[app]
    sddl = BASE.replace(APP, sid)
    assert screen(executable, sddl, sid) == "DENY:APP_IDENTITY_NOT_INDIVIDUAL"
