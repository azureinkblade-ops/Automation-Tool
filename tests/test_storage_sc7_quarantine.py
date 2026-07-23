"""SC-7 reversible quarantine tests (isolated, no live mutation).

Verifies:
- quarantine moves a file to <trash>/<date>/ with a hash-verified manifest
- quarantining again is a no-op (idempotent)
- restore moves it back and verifies the hash matches
- restore refuses on hash mismatch (tamper guard)

Uses an isolated temp trash dir (monkeypatched TRASH_ROOT) so the test never
touches the production _trash-json/ folder or restores real quarantined files.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_qspec = importlib.util.spec_from_file_location("qdj", ROOT / "tools" / "quarantine_dead_json.py")
_q = importlib.util.module_from_spec(_qspec)
_qspec.loader.exec_module(_q)

_rspec = importlib.util.spec_from_file_location("rdj", ROOT / "tools" / "restore_trash_json.py")
_r = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(_r)


def _setup_trash() -> Path:
    trash = Path(tempfile.mkdtemp(prefix="sc7-trash-"))
    _q.TRASH_ROOT = trash
    _r.TRASH_ROOT = trash
    return trash


def _write_victim(name: str, content: str) -> Path:
    # Lives under ROOT so the tool's relative_to(ROOT) works (real usage:
    # quarantined files are repo-root JSON, e.g. posting_schedule.json).
    d = Path(tempfile.mkdtemp(prefix="sc7-src-", dir=str(ROOT)))
    p = d / name
    p.write_text(content, encoding="utf-8")
    return p


def test_quarantine_and_restore_roundtrip():
    trash = _setup_trash()
    victim = _write_victim("dead.json", '{"dead": true}')
    moved = _q.quarantine([victim], reason="test", classification="test")
    assert moved == 1, moved
    assert not victim.exists(), "file should be moved"

    manifests = sorted(trash.glob("*/manifest.json"), key=lambda p: p.parent.name, reverse=True)
    assert manifests, "manifest not written"
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest[0]["hash_match"] is True
    assert "dead.json" in manifest[0]["original_path"]

    # idempotent: quarantining the same (now-missing) path is a no-op
    moved2 = _q.quarantine([victim], reason="test", classification="test")
    assert moved2 == 0, moved2

    # restore
    rc = _r.restore(date=manifests[0].parent.name)
    assert rc == 0
    assert victim.exists(), "file should be restored"
    assert json.loads(victim.read_text(encoding="utf-8")) == {"dead": True}


def test_restore_refuses_hash_mismatch():
    trash = _setup_trash()
    victim = _write_victim("tamper.json", "original")
    _q.quarantine([victim], reason="test", classification="test")
    manifests = sorted(trash.glob("*/manifest.json"), key=lambda p: p.parent.name, reverse=True)
    m = json.loads(manifests[0].read_text(encoding="utf-8"))
    qfile = _q.TRASH_ROOT / m[0]["quarantine_path"]
    qfile.write_text("TAMPERED", encoding="utf-8")  # break hash
    rc = _r.restore(date=manifests[0].parent.name)
    # tampered file must NOT be restored to its original path
    assert not (ROOT / m[0]["original_path"]).exists(), "tampered file must NOT be restored"


def test_quarantine_absent_is_skip():
    _setup_trash()
    missing = ROOT / "does-not-exist-xyz.json"
    moved = _q.quarantine([missing], reason="test")
    assert moved == 0


if __name__ == "__main__":
    raise SystemExit(1)
