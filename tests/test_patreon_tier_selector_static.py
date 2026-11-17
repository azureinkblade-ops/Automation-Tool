# -*- coding: utf-8 -*-
"""Static checks on the generated Patreon Playwright scripts' tier selection (no browser, no node, no network).
The behavioural fixture test lives in grok-jobs/proposed/test_patreon_tier_selector.py (needs node + local Chromium)."""
from __future__ import annotations

BEGIN, END = "// === PATREON TIER HELPERS BEGIN ===", "// === PATREON TIER HELPERS END ==="


def _scripts(tmp_path):
    import app
    f1 = tmp_path / "s1"; f1.mkdir()
    s1 = app.write_chapter_upload_tabs_playwright_script(f1, [{"id": "t", "tiers": ["Inner Disciple"]}]).read_text(encoding="utf-8")
    f2 = tmp_path / "s2"; f2.mkdir()
    s2 = app.write_patreon_draft_playwright_script(f2, {"id": "t", "tiers": ["Inner Disciple"], "access_level": "paid"}).read_text(encoding="utf-8")
    return s1, s2


def _block(js: str) -> str:
    assert BEGIN in js and END in js
    return js[js.index(BEGIN):js.index(END)]


def test_helper_blocks_identical_and_price_agnostic(tmp_path):
    s1, s2 = _scripts(tmp_path)
    b1, b2 = _block(s1), _block(s2)
    assert b1 == b2
    code = "\n".join(l for l in b1.splitlines() if not l.strip().startswith("//"))
    for needle in ['button[aria-label="Select tiers"]', '[role="menuitemcheckbox"]', 'input[type="radio"][value="paid"]',
                   "getAttribute('aria-checked')", "const PATREON_TIER_NAMES = ['Inner Disciple', 'Path Initiate']", "/^select all/i"]:
        assert needle in code, needle
    assert "$3" not in code and "$5" not in code and "/month" not in code
    assert "implied" not in code and "getByText(/^Paid access$/i)" not in code      # Paid is never inferred
    assert "'missing paid access control'" in code


def test_select_all_is_never_clicked_and_read_is_read_only(tmp_path):
    s1, _ = _scripts(tmp_path)
    code = _block(s1)
    items = code[code.index("async function readTierItems"):code.index("async function readPaidAccess")]
    assert "if (!name) continue;" in items            # only the two named tiers are ever returned (not 'ALL')
    cfg = code[code.index("async function configurePatreonTiers"):code.index("async function readPatreonTierState")]
    assert cfg.count(".click(") == 1 and "item.el.click(" in cfg
    ro = code[code.index("async function readPatreonTierState"):]
    assert "item.el.click" not in ro and "entry.el.click" not in ro


def test_gate_contract_unchanged(tmp_path):
    s1, _ = _scripts(tmp_path)
    v = s1[s1.index("async function verifyPatreonDraft"):s1.index("async function verifyPersistedPatreonPost")]
    for needle in ["checks.paidFound = tierState.paid.found", "checks.paidChecked = tierState.paid.checked",
                   "checks.paidAccess = tierState.paid.found && tierState.paid.checked", "checks.tiers = tierState.tiersOk",
                   "checks.tierStates = tierState.states"]:
        assert needle in v, needle
    pv = s1[s1.index("async function verifyPersistedPatreonPost"):s1.index("async function submitPatreonDraft")]
    assert "readback: { bodyWords: readbackBodyWords, tierStates, paidFound: checks.paidFound, paidChecked: checks.paidChecked, mediaStatus: checks.mediaStatus }" in pv
    t = s1[s1.index("async function tryConfigureAudience"):s1.index("async function tryConfigureSchedule")]
    assert t.index("selectPaidAccess") < t.index("enableTierAccess") < t.index("configurePatreonTiers")
    assert "setTierSelection(" not in s1 and "missing paid-member tier access toggle" not in s1
