"""Regression test for the Royal Road publish-verification fix.

Background
----------
A bug caused Royal Road releases to be marked `blocked` even after they had
actually been saved/scheduled. The post-submit verification in app.py relied on
scraping the author-dashboard draft list (`findRoyalRoadChapterInDashboard().found`),
which is fragile on a freshly written row + date-text match. The fix (see
app.py ~lines 29063/29069/29073-29075) ALSO treats a redirect to
`/author-dashboard/chapters/editdraft/<id>` (or `/edit/<id>`) as proof the
chapter was created/saved, independent of the dashboard scrape.

This test locks that behaviour in WITHOUT importing app.py (the verified logic
is async JS embedded in a string inside app.py and only runs in a Playwright
browser context). Instead we:
  1. Extract the real `verified` expression from app.py at test time, so the
     test fails if the production logic silently changes (drift guard).
  2. Evaluate it in Node with simulated submit contexts (no browser needed).
  3. Independently assert the upstream "body file must be > 100 bytes" gate that
     keeps a stub like HA-66 correctly `blocked`.

Run directly:  python tools/test_royal_road_verification.py
Or via pytest: pytest tools/test_royal_road_verification.py
Or via the suite: add check_royal_road_verification to regression_check.run_once
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / "app.py"


# ---------------------------------------------------------------------------
# Extraction of the real verified expression from app.py
# ---------------------------------------------------------------------------
def extract_verified_expression(source: str) -> str:
    """Pull the real JS ternary that computes `verified` for the RR submit step.

    Matches the production source:
        const verified = verification.editExisting
          ? validationErrors.length === 0 && leftNewEditor && leftEditForm
          : validationErrors.length === 0 && (Boolean(dashboardVerification && dashboardVerification.found) || (landedOnSavedDraft && leftNewEditor));
    Returns the JS boolean expression (a `cond ? A : B` ternary) ready to eval.
    """
    pattern = re.compile(
        r"const verified = (verification\.editExisting\s*"
        r"\?[^\n]+\s*"
        r":[^\n]+);",
        re.MULTILINE,
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError("Could not locate the RR `verified` expression in app.py")
    return match.group(1).strip()


def assert_fix_present(source: str) -> None:
    """Drift guard: fail loudly if the landedOnSavedDraft fallback is removed."""
    if "landedOnSavedDraft" not in source:
        raise AssertionError(
            "RR fix regressed: `landedOnSavedDraft` no longer present in app.py. "
            "The post-submit verification will again false-block published chapters."
        )
    if "(editdraft|edit)" not in source:
        raise AssertionError(
            "RR fix regressed: the editdraft/edit redirect regex is gone from app.py."
        )


# ---------------------------------------------------------------------------
# Node evaluation of the extracted expression
# ---------------------------------------------------------------------------
def evaluate_verified(expression_js: str, ctx: dict) -> bool:
    """Evaluate the extracted `verified` expression in Node with a given context."""
    ctx_json = __import__("json").dumps(ctx)
    program = (
        "const ctx = " + ctx_json + ";\n"
        "const verification = ctx.verification;\n"
        "const validationErrors = ctx.validationErrors;\n"
        "const dashboardVerification = ctx.dashboardVerification;\n"
        "const landedOnSavedDraft = ctx.landedOnSavedDraft;\n"
        "const leftNewEditor = ctx.leftNewEditor;\n"
        "const leftEditForm = ctx.leftEditForm;\n"
        "const verified = " + expression_js + ";\n"
        "process.stdout.write(String(verified));\n"
    )
    proc = subprocess.run(
        ["node", "-e", program],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node eval failed: {proc.stderr}")
    return proc.stdout.strip().lower() == "true"


def build_ctx(
    *,
    edit_existing: bool,
    after_url: str,
    dashboard_found: bool | None,
    validation_errors: int = 0,
    left_new_editor: bool = True,
    left_edit_form: bool = True,
):
    """Construct the submit context the RR worker computes after a submit."""
    landed_on_saved_draft = bool(
        re.search(r"/author-dashboard/chapters/(editdraft|edit)/", after_url)
    )
    return {
        "verification": {"editExisting": edit_existing},
        "validationErrors": ["x"] * max(0, validation_errors),
        "dashboardVerification": (
            {"found": bool(dashboard_found)} if dashboard_found is not None else None
        ),
        "landedOnSavedDraft": landed_on_saved_draft,
        "leftNewEditor": left_new_editor,
        "leftEditForm": left_edit_form,
    }


# ---------------------------------------------------------------------------
# Upstream stub-body gate (mirrors app.py line ~21947)
# ---------------------------------------------------------------------------
def body_gate_passes(body_bytes: int) -> bool:
    """Mirror of app.py: a Royal Road release is blocked unless a body file > 100 bytes."""
    return body_bytes > 100


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
def test_rr_fix_extraction_and_drift_guard():
    source = APP_PY.read_text(encoding="utf-8")
    assert_fix_present(source)
    expr = extract_verified_expression(source)
    assert "landedOnSavedDraft" in expr
    assert "dashboardVerification" in expr


def test_rr_fix_new_chapter_landed_on_editdraft_is_verified():
    """The actual fix: a new chapter that redirects to /editdraft/<id> is verified
    even when the dashboard scrape has not yet indexed the fresh row."""
    source = APP_PY.read_text(encoding="utf-8")
    expr = extract_verified_expression(source)
    ctx = build_ctx(
        edit_existing=False,
        after_url="https://www.royalroad.com/author-dashboard/chapters/editdraft/1685911",
        dashboard_found=None,  # dashboard scrape not yet positive
        validation_errors=0,
        left_new_editor=True,
    )
    assert evaluate_verified(expr, ctx) is True


def test_rr_fix_editdraft_alias_edit_is_verified():
    """Same guard for the published-chapter /edit/<id> redirect path."""
    source = APP_PY.read_text(encoding="utf-8")
    expr = extract_verified_expression(source)
    ctx = build_ctx(
        edit_existing=False,
        after_url="https://www.royalroad.com/author-dashboard/chapters/edit/1685911",
        dashboard_found=False,
        validation_errors=0,
        left_new_editor=True,
    )
    assert evaluate_verified(expr, ctx) is True


def test_rr_fix_dashboard_found_is_verified():
    """Original path still works: dashboard scrape found the row."""
    source = APP_PY.read_text(encoding="utf-8")
    expr = extract_verified_expression(source)
    ctx = build_ctx(
        edit_existing=False,
        after_url="https://www.royalroad.com/author-dashboard/chapters/new/",
        dashboard_found=True,
        validation_errors=0,
    )
    assert evaluate_verified(expr, ctx) is True


def test_rr_fix_not_verified_when_no_proof():
    """A new chapter that neither landed on a draft edit page nor was found in the
    dashboard stays NOT verified (no false success)."""
    source = APP_PY.read_text(encoding="utf-8")
    expr = extract_verified_expression(source)
    ctx = build_ctx(
        edit_existing=False,
        after_url="https://www.royalroad.com/author-dashboard/chapters/new/",
        dashboard_found=False,
        validation_errors=0,
        left_new_editor=False,
    )
    assert evaluate_verified(expr, ctx) is False


def test_rr_fix_validation_error_blocks():
    """Even a redirect to editdraft does not verify if there were validation errors."""
    source = APP_PY.read_text(encoding="utf-8")
    expr = extract_verified_expression(source)
    ctx = build_ctx(
        edit_existing=False,
        after_url="https://www.royalroad.com/author-dashboard/chapters/editdraft/1685911",
        dashboard_found=None,
        validation_errors=2,
        left_new_editor=True,
    )
    assert evaluate_verified(expr, ctx) is False


def test_rr_fix_edit_existing_path():
    """Edit-existing path: verified when no validation errors and both left* flags set."""
    source = APP_PY.read_text(encoding="utf-8")
    expr = extract_verified_expression(source)
    ctx = build_ctx(
        edit_existing=True,
        after_url="https://www.royalroad.com/author-dashboard/chapters/edit/12345",
        dashboard_found=None,
        validation_errors=0,
        left_new_editor=True,
        left_edit_form=True,
    )
    assert evaluate_verified(expr, ctx) is True


def test_rr_stub_body_gate_blocks_short_file():
    """HA-66 guard: a 20-byte stub body file must NOT pass the release gate."""
    assert body_gate_passes(20) is False
    assert body_gate_passes(100) is False  # boundary: must be strictly > 100
    assert body_gate_passes(101) is True
    # Real chapter bodies (SF-87 was ~10.5k bytes) always pass.
    assert body_gate_passes(10532) is True


def test_rr_stub_body_gate_matches_production_logic():
    """Guard the production line itself: assert the `> 100` threshold is present."""
    source = APP_PY.read_text(encoding="utf-8")
    assert "st_size > 100" in source, (
        "RR body gate regressed: the `st_size > 100` threshold is gone from app.py. "
        "Stub bodies (e.g. HA-66) could be force-verified."
    )


# ---------------------------------------------------------------------------
# Direct runner (no pytest needed)
# ---------------------------------------------------------------------------
def _run_all() -> int:
    tests = [
        test_rr_fix_extraction_and_drift_guard,
        test_rr_fix_new_chapter_landed_on_editdraft_is_verified,
        test_rr_fix_editdraft_alias_edit_is_verified,
        test_rr_fix_dashboard_found_is_verified,
        test_rr_fix_not_verified_when_no_proof,
        test_rr_fix_validation_error_blocks,
        test_rr_fix_edit_existing_path,
        test_rr_stub_body_gate_blocks_short_file,
        test_rr_stub_body_gate_matches_production_logic,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {test.__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(_run_all())
