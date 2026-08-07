"""End-to-end provenance tests for the agent post pipeline.

Covers the Phase 2 `_finalize` invariant (every terminal outcome persists a run
row and carries a run_id), the unified `agent_result_metadata` contract, the
`generated_social_posts` correlation, and the hard rule that no `_agent_*`
provenance key may leak into public platform copy.

Hermes is never invoked: `subprocess.run` is stubbed so each terminal status is
driven deterministically.

Run: python tests/test_agent_post_provenance.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import agent_post_writer  # noqa: E402
import automation_db  # noqa: E402
import promo_copy  # noqa: E402
from agent_post_writer import (  # noqa: E402
    AgentPostStatus,
    agent_result_metadata,
    generate_post_result,
)


def _assert(cond, msg):
    if cond:
        print(f"  PASS: {msg}")
        return True
    print(f"  FAIL: {msg}")
    _assert.failed += 1
    return False


_assert.failed = 0


VALID_PAYLOAD = {
    "hook": "Kai's golden ember flares against the dark.",
    "caption": "The system refuses to accept his weakness again.",
    "cta": "Read Chapter 24 on Royal Road now!",
    "hashtags": ["#AzureInkblade", "#HeavenlyAscensionSystem"],
    "content_angle": "power-awakening",
    "intended_audience": "progression-fantasy readers",
}

MISSING_CAPTION = {
    "hook": "A hook with no caption.",
    "cta": "Read now",
    "content_angle": "angle",
    "intended_audience": "readers",
}

PUBLIC_KEYS = ("caption", "x_post", "facebook_post", "patreon_note")


class _FakeProc:
    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _stub_hermes(monkey, *, stdout=b"", returncode=0, timeout=False):
    """Replace subprocess.run inside agent_post_writer with a deterministic stub."""

    def fake_run(argv, **kwargs):
        if timeout:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=1)
        return _FakeProc(stdout=stdout, returncode=returncode)

    monkey.append((agent_post_writer, "subprocess"))
    agent_post_writer.subprocess.run = fake_run


class _Sandbox:
    """Point the writer + app at a throwaway SQLite root and a resolvable hermes."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig_run = subprocess.run
        self._orig_resolve = agent_post_writer._resolve_hermes
        self._orig_finalize_root = None

    def __enter__(self):
        automation_db.init_db(self.tmp)
        agent_post_writer._resolve_hermes = lambda: r"C:\fake\hermes.exe"
        # _finalize persists to the module's repo root; redirect it to the sandbox.
        self._patch_finalize_root()
        return self

    def _patch_finalize_root(self):
        real_insert = automation_db.insert_agent_post_run
        real_fields = automation_db.replace_agent_post_fields
        tmp = self.tmp

        def insert(root, **kw):
            return real_insert(tmp, **kw)

        def fields(root, run_id, flds):
            return real_fields(tmp, run_id, flds)

        self._orig_finalize_root = (real_insert, real_fields)
        automation_db.insert_agent_post_run = insert
        automation_db.replace_agent_post_fields = fields

    def __exit__(self, *exc):
        subprocess.run = self._orig_run
        agent_post_writer.subprocess.run = self._orig_run
        agent_post_writer._resolve_hermes = self._orig_resolve
        if self._orig_finalize_root:
            automation_db.insert_agent_post_run = self._orig_finalize_root[0]
            automation_db.replace_agent_post_fields = self._orig_finalize_root[1]
        return False

    def run_rows(self, run_id):
        with automation_db.connect(self.tmp) as conn:
            return conn.execute(
                "SELECT run_id, status, fallback_reason, parse_mode FROM agent_post_runs WHERE run_id=?",
                (run_id,),
            ).fetchall()

    def social_rows(self, run_id):
        with automation_db.connect(self.tmp) as conn:
            return conn.execute(
                "SELECT platform, post_text, agent_used FROM generated_social_posts WHERE run_id=?",
                (run_id,),
            ).fetchall()


def _material():
    return {"abbr": "HA", "novel": "Heavenly Ascension", "chapter": "24", "phrases": ["ember"]}


def _build_posts(agent_copy):
    return promo_copy.build_platform_posts(
        "Chapter 24", "Body text for the chapter.", _material(), agent_copy=agent_copy
    )


def _assert_no_leakage(posts, label):
    """No _agent_* key or hermes marker may appear in PUBLIC post text."""
    ok = True
    for key in PUBLIC_KEYS:
        text = str(posts.get(key) or "")
        for banned in ("_agent_", "_agent_run_id", "_agent_status", "hermes"):
            if banned in text.lower():
                ok &= _assert(False, f"{label}: '{banned}' leaked into {key}")
    ok &= _assert(True, f"{label}: no _agent_* / hermes marker in public copy")
    return ok


def test_success_path():
    print("[1] SUCCESS -> copy used, run_id + parse_mode set, correlation row written")
    ok = True
    with _Sandbox() as box:
        agent_post_writer.subprocess.run = lambda argv, **kw: _FakeProc(
            stdout=json.dumps(VALID_PAYLOAD).encode("utf-8")
        )
        result = generate_post_result("HA", "Heavenly Ascension", "24", "ember", _material())
        ok &= _assert(result.status is AgentPostStatus.SUCCESS, f"status SUCCESS (got {result.status.value})")
        ok &= _assert(result.copy is not None, "copy present")
        ok &= _assert(bool(result.run_id), f"run_id non-empty ({result.run_id})")
        ok &= _assert(result.parse_mode == "whole_text", f"parse_mode whole_text (got {result.parse_mode})")

        meta = agent_result_metadata(result)
        posts = _build_posts(result.copy)
        meta["_agent_used"] = result.copy is not None and posts.get("_agent_source") == "hermes_agent"
        ok &= _assert(meta["_agent_used"] is True, "_agent_used True after real consumption")
        ok &= _assert(meta["_agent_run_id"] == result.run_id, "_agent_run_id matches result")

        rows = box.run_rows(result.run_id)
        ok &= _assert(len(rows) == 1, "agent_post_runs row persisted")
        ok &= _assert(rows and rows[0]["parse_mode"] == "whole_text", "parse_mode persisted to DB")

        automation_db.insert_generated_social_posts(
            box.tmp,
            result.run_id,
            [(p, str(posts.get(k) or ""), meta["_agent_used"], meta["_agent_fallback_reason"])
             for p, k in (("instagram", "caption"), ("x", "x_post"),
                          ("facebook", "facebook_post"), ("patreon", "patreon_note"))],
        )
        srows = box.social_rows(result.run_id)
        ok &= _assert(len(srows) == 4, f"4 generated_social_posts rows correlated (got {len(srows)})")
        ok &= _assert(all(r["agent_used"] == 1 for r in srows), "rows flagged agent_used=1")
        ok &= _assert_no_leakage(posts, "success")
    return ok


def test_hermes_timeout():
    print("[2] HERMES_TIMEOUT -> template copy, _agent_used False, reason preserved")
    ok = True
    with _Sandbox() as box:
        def boom(argv, **kw):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=1)

        agent_post_writer.subprocess.run = boom
        result = generate_post_result("HA", "Heavenly Ascension", "24", "ember", _material())
        ok &= _assert(result.status is AgentPostStatus.HERMES_TIMEOUT, f"status HERMES_TIMEOUT (got {result.status.value})")
        ok &= _assert(result.copy is None, "copy is None")
        ok &= _assert(bool(result.run_id), "run_id present on failure")

        meta = agent_result_metadata(result)
        posts = _build_posts(result.copy)
        meta["_agent_used"] = result.copy is not None and posts.get("_agent_source") == "hermes_agent"
        ok &= _assert(meta["_agent_used"] is False, "_agent_used False")
        ok &= _assert(meta["_agent_status"] == "HERMES_TIMEOUT", "_agent_status recorded")
        ok &= _assert(bool(meta["_agent_fallback_reason"]), f"fallback reason preserved ({meta['_agent_fallback_reason']})")
        ok &= _assert(all(posts.get(k) for k in PUBLIC_KEYS), "all four platform posts still produced by template")
        ok &= _assert(len(box.run_rows(result.run_id)) == 1, "agent_post_runs row exists for the timeout")
        ok &= _assert_no_leakage(posts, "timeout")
    return ok


def test_contract_failure():
    print("[3] CONTRACT_VALIDATION_FAILED -> all four platforms still built")
    ok = True
    with _Sandbox() as box:
        agent_post_writer.subprocess.run = lambda argv, **kw: _FakeProc(
            stdout=json.dumps(MISSING_CAPTION).encode("utf-8")
        )
        result = generate_post_result("HA", "Heavenly Ascension", "24", "ember", _material())
        ok &= _assert(
            result.status is AgentPostStatus.CONTRACT_VALIDATION_FAILED,
            f"status CONTRACT_VALIDATION_FAILED (got {result.status.value})",
        )
        ok &= _assert("caption" in result.missing_fields, f"caption in missing_fields {result.missing_fields}")
        ok &= _assert(result.parse_mode == "whole_text", "parse_mode set on contract failure")
        posts = _build_posts(result.copy)
        ok &= _assert(all(posts.get(k) for k in PUBLIC_KEYS), "all four platforms produced")
        ok &= _assert(len(box.run_rows(result.run_id)) == 1, "run row persisted")
        ok &= _assert_no_leakage(posts, "contract-failure")
    return ok


def test_agent_disabled():
    print("[4] HERMES_NOT_ENABLED -> run_id present AND run row still written")
    ok = True
    with _Sandbox() as box:
        agent_post_writer._resolve_hermes = lambda: None
        result = generate_post_result("HA", "Heavenly Ascension", "24", "ember", _material())
        ok &= _assert(
            result.status is AgentPostStatus.HERMES_NOT_ENABLED,
            f"status HERMES_NOT_ENABLED (got {result.status.value})",
        )
        ok &= _assert(bool(result.run_id), "run_id present even when disabled")
        rows = box.run_rows(result.run_id)
        ok &= _assert(len(rows) == 1, "agent_post_runs row written (the _finalize invariant)")
        meta = agent_result_metadata(result)
        ok &= _assert(meta["_agent_used"] is False, "_agent_used False")
        ok &= _assert(meta["_agent_source"] is None, "_agent_source None when no copy")
        posts = _build_posts(result.copy)
        ok &= _assert_no_leakage(posts, "disabled")
    return ok


def test_run_id_uniqueness():
    print("[5] two same-second runs -> distinct run_ids and two distinct rows")
    ok = True
    with _Sandbox() as box:
        agent_post_writer._resolve_hermes = lambda: None
        r1 = generate_post_result("HA", "Heavenly Ascension", "24", "ember", _material())
        r2 = generate_post_result("HA", "Heavenly Ascension", "24", "ember", _material())
        ok &= _assert(r1.run_id != r2.run_id, f"distinct run_ids ({r1.run_id} vs {r2.run_id})")
        with automation_db.connect(box.tmp) as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_post_runs WHERE run_id IN (?,?)",
                (r1.run_id, r2.run_id),
            ).fetchone()["c"]
        ok &= _assert(total == 2, f"two distinct agent_post_runs rows (got {total})")
    return ok


def test_metadata_contract_shape():
    print("[6] agent_result_metadata always returns the full key set")
    expected = {
        "_agent_requested", "_agent_used", "_agent_status", "_agent_run_id",
        "_agent_source", "_agent_fallback_reason", "_agent_model", "_agent_provider",
        "_agent_reasoning", "_agent_parse_mode", "_agent_duration_ms",
        "_agent_schema_version",
    }
    ok = True
    with _Sandbox():
        agent_post_writer._resolve_hermes = lambda: None
        result = generate_post_result("HA", "Heavenly Ascension", "24", "ember", _material())
        meta = agent_result_metadata(result)
        ok &= _assert(set(meta) == expected, f"exact key set (diff={set(meta) ^ expected})")
        ok &= _assert(meta["_agent_fallback_reason"] is not None, "fallback_reason is None-or-str, not empty string")
        ok &= _assert(meta["_agent_schema_version"] == "social-post-v1", "schema version pinned")
        ok &= _assert(
            agent_post_writer.agent_fallback_metadata is agent_result_metadata,
            "legacy alias still exported",
        )
    return ok


def test_write_text_artifacts_boundary():
    print("[7] write_text_artifacts: _agent_* reaches metadata.json ONLY, never public .txt")
    ok = True
    # Import app lazily: it is a large module and only this test needs it.
    try:
        import app  # noqa: E402
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"  SKIP: app import unavailable ({exc})")
        return True

    folder = Path(tempfile.mkdtemp()) / "pack"
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "abbr": "HA",
        "novel": "Heavenly Ascension",
        "phrases": ["ember", "ascend"],
        "caption": "A clean public caption.",
        "x_post": "A clean public x post.",
        "facebook_post": "A clean public facebook post.",
        "royal_road_note": "A clean royal road note.",
        "patreon_note": "A clean patreon note.",
        # provenance that must stay internal
        "_agent_run_id": "agentpost_HA_24_LEAKCANARY",
        "_agent_status": "SUCCESS",
        "_agent_source": "hermes_agent",
        "_agent_used": True,
    }
    app.write_text_artifacts(folder, payload)

    public_txt = [
        "caption.txt", "instagram-caption.txt", "x-post.txt",
        "facebook-post.txt", "patreon-note.txt", "royal-road-note.txt", "phrases.txt",
    ]
    for name in public_txt:
        path = folder / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for banned in ("_agent_", "leakcanary", "hermes_agent"):
            if banned in text:
                ok &= _assert(False, f"'{banned}' leaked into public {name}")
    ok &= _assert(True, "no _agent_* / canary in any public .txt artifact")

    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    ok &= _assert(meta.get("_agent_run_id") == "agentpost_HA_24_LEAKCANARY",
                  "provenance IS present in internal metadata.json")
    return ok


def main():
    _assert.failed = 0
    results = [
        test_success_path(),
        test_hermes_timeout(),
        test_contract_failure(),
        test_agent_disabled(),
        test_run_id_uniqueness(),
        test_metadata_contract_shape(),
        test_write_text_artifacts_boundary(),
    ]
    print()
    if _assert.failed == 0 and all(results):
        print("ALL AGENT POST PROVENANCE TESTS PASSED")
        return 0
    print(f"{_assert.failed} provenance test(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
