r"""Replace ONE existing chapter in a GitHub Docs novel .docx (mid-book), without touching app.py.

The import path in app.py (import_manual_written_chapter -> append_chapter_to_github_docs) is append-only and returns
BLOCKED_DUPLICATE for a chapter that already exists. This standalone tool does the "swap" case:

  1. backs up (Docs .docx + GitHub blob/commit SHAs, old chapter folder, ledger/continuity/queue entries, word counts)
     into backups/<name>/ with a restore script;
  2. splices ONLY the old chapter's paragraphs in word/document.xml, using the same paragraph markup as
     app.docx_paragraph_xml / append_chapter_to_docx (heading paragraph = Heading1 style, body = plain paragraphs);
  3. proves every other chapter is text-identical before/after (and the XML outside the splice is byte-identical);
  4. uploads through app.upload_bytes_to_github (the exact commit path the append uses) and reads it back;
  5. writes a NEW chapters/*-manual folder (old folder stays on disk), updates the chapter ledger entry
     (written=True, writeMode=manual_chatgpt) and the saved word count (chapter_word_counts.record_import),
     and replaces ONLY that chapter's entry in continuity recent_chapters (never rolls last_chapter back).

Dry run by default (read-only, writes nothing). Never posts or releases anything and never prints credentials.
Usage:  .venv-gpu\Scripts\python.exe tools\replace_written_chapter.py HP 154 grok-jobs\drafts\HP-154.md [--apply]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PARA_RE = re.compile(r"<w:p[ >][\s\S]*?</w:p>|<w:p/>")
POSTED_KEYS = ("postedToPatreon", "postedToRoyalRoad", "patreonInnerDisciplePosted", "patreonPathInitiatePosted", "patreonDraftPrepared", "royalRoadUploadPrepared")
FOLDER_SLUGS = {"EN": "eternal-nexus", "HP": "hundredfold-path", "HA": "heavenly-ascension-system", "SF": "soul-forge-era"}


class ReplaceError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- pure helpers
def sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def count_words(text: str) -> int:
    """Same definition as chapter_word_counts.words()."""
    return len(re.findall(r"\w+", text or ""))


def paragraph_text(pxml: str) -> str:
    wrapped = '<r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' + pxml + "</r>"
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for node in root.iter():
        if node.tag == f"{W}t":
            parts.append(node.text or "")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
        elif node.tag == f"{W}tab":
            parts.append("\t")
    return "".join(parts)


def chapter_paragraphs(title: str, chapter_text: str) -> list[str]:
    """Paragraph list exactly as app.append_chapter_to_docx builds it: [title] + blank-line separated parts."""
    title = title.strip() or "New Chapter"
    paragraphs = [title] + [p.strip() for p in re.split(r"\n\s*\n+", chapter_text.strip()) if p.strip()]
    if len(paragraphs) > 1 and paragraphs[1].strip().lower() == title.lower():
        paragraphs.pop(1)
    return paragraphs


def build_insert_xml(title: str, chapter_text: str, paragraph_xml: Callable[..., str]) -> tuple[str, list[str]]:
    paragraphs = chapter_paragraphs(title, chapter_text)
    return "".join(paragraph_xml(p, heading=(i == 0)) for i, p in enumerate(paragraphs)), paragraphs


def find_chapter_span(xml: str, number: int, heading_info: Callable[[str], Optional[tuple[int, str]]]) -> dict[str, Any]:
    """Char span [start, end) in document.xml of the body-level paragraphs of chapter `number`.

    start = first heading paragraph whose chapter number == number; end = first later heading paragraph with a different
    number (or the final sectPr / </w:body>). Sub-parts ("Chapter 154 Part 2") share the number and stay inside the span."""
    if "txbxContent" in xml:
        raise ReplaceError("document.xml has text boxes (nested paragraphs); string splice is not safe")
    body_end = xml.rfind("</w:body>")
    if body_end < 0:
        raise ReplaceError("document.xml has no </w:body>")
    sect = xml.rfind("<w:sectPr", 0, body_end)
    limit = sect if sect > 0 else body_end
    start: Optional[int] = None
    end: Optional[int] = None
    headings_in_span: list[int] = []
    for m in PARA_RE.finditer(xml[:limit]):
        first = paragraph_text(m.group(0)).split("\n")[0].strip()
        info = heading_info(first) if first else None
        if info is None:
            continue
        if start is None:
            if info[0] == number:
                start = m.start()
                headings_in_span.append(info[0])
        elif info[0] != number:
            end = m.start()
            break
        else:
            headings_in_span.append(info[0])
    if start is None:
        raise ReplaceError(f"no heading paragraph for chapter {number} found")
    if end is None:
        end = limit
    removed = xml[start:end]
    if "<w:sectPr" in removed:
        raise ReplaceError("section break inside the span to replace")
    if "<w:tbl" in removed:
        raise ReplaceError("table inside the span to replace")
    texts = [paragraph_text(m.group(0)) for m in PARA_RE.finditer(removed)]
    return {"start": start, "end": end, "removed_xml_chars": len(removed), "removed_paragraphs": len(texts),
            "removed_words": count_words("\n".join(texts)), "headings_in_span": headings_in_span,
            "removed_head": norm(texts[0])[:80] if texts else ""}


def splice_docx(raw: bytes, number: int, title: str, chapter_text: str, *, heading_info, paragraph_xml) -> tuple[bytes, dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    span = find_chapter_span(xml, number, heading_info)
    insert_xml, paragraphs = build_insert_xml(title, chapter_text, paragraph_xml)
    new_xml = xml[: span["start"]] + insert_xml + xml[span["end"]:]
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = new_xml.encode("utf-8")
            zout.writestr(item, data)
    new_raw = out.getvalue()
    errs = verify_splice_bytes(raw, new_raw, span, len(insert_xml))
    if errs:
        raise ReplaceError("splice self-check failed: " + "; ".join(errs))
    span = dict(span, inserted_paragraphs=len(paragraphs), inserted_xml_chars=len(insert_xml),
                new_heading=paragraphs[0], new_words=count_words("\n".join(paragraphs)))
    return new_raw, span


def verify_splice_bytes(old_raw: bytes, new_raw: bytes, span: dict[str, Any], inserted_chars: int) -> list[str]:
    errs: list[str] = []
    with zipfile.ZipFile(io.BytesIO(old_raw)) as a, zipfile.ZipFile(io.BytesIO(new_raw)) as b:
        if [i.filename for i in a.infolist()] != [i.filename for i in b.infolist()]:
            errs.append("zip member list differs")
        for item in a.infolist():
            if item.filename != "word/document.xml" and a.read(item.filename) != b.read(item.filename):
                errs.append(f"zip member changed: {item.filename}")
        ox, nx = a.read("word/document.xml").decode("utf-8"), b.read("word/document.xml").decode("utf-8")
    if ox[: span["start"]] != nx[: span["start"]]:
        errs.append("XML before the splice is not byte-identical")
    if ox[span["end"]:] != nx[span["start"] + inserted_chars:]:
        errs.append("XML after the splice is not byte-identical")
    return errs


def chapters_from_bytes(app_mod, abbr: str, raw: bytes) -> dict[str, Any]:
    """Parse a docx with app.py's own chapter logic on local bytes (no network)."""
    a = app_mod
    path = a.DOCS_NOVEL_FILES[abbr]
    paras = a.docx_paragraphs(raw)
    orig_fc, orig_dp = a.docs_file_content, a.docx_paragraphs
    try:
        a.docs_file_content = lambda p: raw if p == path else orig_fc(p)
        a.docx_paragraphs = lambda r: paras if r is raw else orig_dp(r)
        idx = a.docs_chapter_index(abbr).get("chapters", [])
        nums = [int(c["number"]) for c in idx if str(c.get("number", "")).lstrip("-").isdigit()]
        out: dict[int, dict[str, Any]] = {}
        for n in sorted(set(nums)):
            d = a.docs_chapter_text(abbr, n)
            out[n] = {"title": d.get("title"), "sha_raw": sha256(d.get("raw_text") or ""), "sha_text": sha256(d.get("text") or ""),
                      "raw_text": d.get("raw_text") or "", "heading": d.get("heading")}
        return {"numbers_in_order": nums, "max": max(nums) if nums else 0, "chapters": out}
    finally:
        a.docs_file_content, a.docx_paragraphs = orig_fc, orig_dp


def compare_other_chapters(before: dict[str, Any], after: dict[str, Any], number: int) -> list[str]:
    errs: list[str] = []
    if before["numbers_in_order"] != after["numbers_in_order"]:
        errs.append(f"chapter list changed: before={before['numbers_in_order'][-6:]} after={after['numbers_in_order'][-6:]}")
    for n, b in before["chapters"].items():
        if n == number:
            continue
        c = after["chapters"].get(n)
        if not c or c["sha_raw"] != b["sha_raw"] or c["sha_text"] != b["sha_text"]:
            errs.append(f"chapter {n} text changed")
    if number not in after["chapters"]:
        errs.append(f"chapter {number} missing after splice")
    return errs


def docs_body_matches_draft(docs_raw_text: str, heading: str, draft_body: str, tolerance: int = 15) -> list[str]:
    """Docs chapter text (heading + body) must equal the draft body; same tolerance rule as the Nov 10 importer verify."""
    errs: list[str] = []
    dbody = docs_raw_text.strip()
    lines = dbody.splitlines()
    if lines and (norm(lines[0]) == norm(heading) or re.match(r"^\s*chapter\s+\d+", lines[0], re.IGNORECASE)):
        dbody = "\n".join(lines[1:])
    dbody = re.sub(r'([.!?,]) "(?=\s|$)', r'\1"', dbody)  # app normalizer spaces closing straight quotes (house artifact)
    draft_body = re.sub(r'([.!?,]) "(?=\s|$)', r'\1"', draft_body)
    dw, sw = len(norm(dbody).split()), len(norm(draft_body).split())
    if abs(dw - sw) > tolerance:
        errs.append(f"word count docs {dw} vs draft {sw}")
    if norm(dbody)[:200] != norm(draft_body)[:200]:
        errs.append("docs chapter opening differs from the draft")
    return errs


def continuity_replace_recent(snapshot: dict[str, Any], number: int, title: str, summary: str) -> tuple[dict[str, Any], bool]:
    """Replace ONLY the recent_chapters entry for `number`; last_chapter / last_title / next setup are left untouched."""
    snap = dict(snapshot)
    recent = [dict(x) if isinstance(x, dict) else x for x in (snap.get("recent_chapters") or [])]
    hit = False
    for entry in recent:
        if isinstance(entry, dict) and str(entry.get("chapter")) == str(number):
            entry.update({"title": title, "summary": summary})
            hit = True
    snap["recent_chapters"] = recent
    return snap, hit


def release_job_report(db_path: Path, abbr: str, number: int, old_snippets: list[str], new_title: str) -> list[dict[str, Any]]:
    """Read-only: does any release job row hold its own copy of chapter text? (payload long strings / old snippets)."""
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = []
    try:
        for r in con.execute("select * from release_automation_jobs where novel_abbr=? and chapter_number=? order by scheduled_for", (abbr, number)):
            d = dict(r)
            blob = d.get("payload_json") or ""
            try:
                payload = json.loads(blob)
            except Exception:
                payload = {}
            long_fields = {k: len(v) for k, v in payload.items() if isinstance(v, str) and len(v) > 300}
            all_text = blob + " " + str(d.get("last_error") or "")
            hits = [s[:40] for s in old_snippets if s and s in all_text]
            rows.append({"job_id": d["job_id"], "stage": d["stage"], "status": d["status"], "scheduled_for": d["scheduled_for"],
                         "payload_keys": sorted(payload.keys()), "long_text_fields": long_fields, "old_text_snippets_found": hits,
                         "payload_title": payload.get("title"), "payload_title_matches_new": norm(str(payload.get("title") or "")) == norm(new_title),
                         "holds_own_copy": bool(long_fields or hits)})
    finally:
        con.close()
    return rows


# ----------------------------------------------------------------------------- app access (lazy; tests inject a module)
def load_app():
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import app as a  # noqa: WPS433 - heavy import, only when running for real

    a.load_env_file()
    a.wire_extracted_modules()
    return a


def docs_branch() -> str:
    return (os.environ.get("GITHUB_DOCS_BRANCH") or os.environ.get("GITHUB_BRANCH") or "main").strip() or "main"


def github_meta(a, repo_path: str) -> dict[str, Any]:
    enc, br = urllib.parse.quote(repo_path, safe="/"), docs_branch()
    base = f"/repos/{a.DOCS_REPO_OWNER}/{a.DOCS_REPO_NAME}"
    c = a.github_api_request("GET", f"{base}/contents/{enc}?ref={urllib.parse.quote(br)}")
    commits = a.github_api_request("GET", f"{base}/commits?path={urllib.parse.quote(repo_path)}&sha={urllib.parse.quote(br)}&per_page=1")
    head = a.github_api_request("GET", f"{base}/commits/{urllib.parse.quote(br)}")
    return {"repo": f"{a.DOCS_REPO_OWNER}/{a.DOCS_REPO_NAME}", "branch": br, "path": repo_path, "blob_sha": c.get("sha"), "size": c.get("size"),
            "last_commit_sha": (commits[0]["sha"] if isinstance(commits, list) and commits else None), "branch_head_sha": head.get("sha")}


def fetch_docs_bytes(a, repo_path: str) -> bytes:
    """Read through the Contents API on the Docs branch (what an upload would overwrite), not the raw.githubusercontent cache."""
    enc = urllib.parse.quote(repo_path, safe="/")
    base = f"/repos/{a.DOCS_REPO_OWNER}/{a.DOCS_REPO_NAME}"
    data = a.github_api_request("GET", f"{base}/contents/{enc}?ref={urllib.parse.quote(docs_branch())}")
    import base64

    if data.get("content"):
        return base64.b64decode(data["content"])
    blob = a.github_api_request("GET", f"{base}/git/blobs/{data['sha']}")
    return base64.b64decode(blob["content"])


# ----------------------------------------------------------------------------- backup + restore
RESTORE_PY = r'''"""Restore for tools/replace_written_chapter.py (generated). Usage: python restore.py [--skip-docs]
Local files are copied back from this folder. The Docs file is re-uploaded only when GitHub still holds the blob this tool wrote
(otherwise someone changed it since and it stops)."""
import json, os, shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
M = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
ROOT = Path(M["root"])
os.chdir(ROOT); sys.path.insert(0, str(ROOT))
skip_docs = "--skip-docs" in sys.argv
import chapter_word_counts as cwc
wc_path = ROOT / "chapter_word_counts.json"
if (HERE / "chapter_word_counts.json").exists():
    shutil.copy2(HERE / "chapter_word_counts.json", wc_path); print("restored chapter_word_counts.json")
cont_src = HERE / M["continuity_file"]
if cont_src.exists():
    shutil.copy2(cont_src, ROOT / "continuity" / M["continuity_file"]); print("restored continuity", M["continuity_file"])
import app as a
a.load_env_file(); a.wire_extracted_modules()
old = M["ledger_before"]
if old:
    restore = dict(old); [restore.setdefault(k, None) for k in M.get("ledger_added_keys", [])]
    a.update_chapter_ledger(M["abbr"], M["number"], restore); print("restored ledger entry", M["abbr"], M["number"])
if not skip_docs and M.get("docs_after_blob_sha"):
    cur = a.github_existing_sha(a.DOCS_REPO_OWNER, a.DOCS_REPO_NAME, M["docs"]["path"], M["docs"]["branch"])
    if cur != M["docs_after_blob_sha"]:
        raise SystemExit("Docs blob changed since this tool wrote it; not restoring the Docs file automatically.")
    raw = (HERE / M["docs_backup_file"]).read_bytes()
    r = a.upload_bytes_to_github(raw, M["docs"]["path"], "Restore " + M["abbr"] + " chapter " + str(M["number"]) + " (undo replace)", owner=a.DOCS_REPO_OWNER, repo=a.DOCS_REPO_NAME, branch=M["docs"]["branch"])
    print("restored Docs file; commit", (r.get("commit") or {}).get("sha") if isinstance(r, dict) and isinstance(r.get("commit"), dict) else r.get("commit"))
print("new chapter folder left on disk:", M.get("new_folder"))
'''


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def make_backup(a, backup_dir: Path, abbr: str, number: int, raw: bytes, meta: dict[str, Any], old_folder: Optional[Path], ledger_entry: dict[str, Any],
                root: Path) -> dict[str, Any]:
    if backup_dir.exists() and any(backup_dir.iterdir()):
        raise ReplaceError(f"backup dir {backup_dir} already exists and is not empty; refusing to overwrite")
    backup_dir.mkdir(parents=True, exist_ok=True)
    docs_name = Path(meta["path"]).name
    (backup_dir / docs_name).write_bytes(raw)
    if old_folder and old_folder.exists():
        shutil.copytree(old_folder, backup_dir / "old-chapter-folder" / old_folder.name)
    cont_name = f"{abbr}-summary.json"
    cont_src = root / "continuity" / cont_name
    if cont_src.exists():
        shutil.copy2(cont_src, backup_dir / cont_name)
    wc = root / "chapter_word_counts.json"
    if wc.exists():
        shutil.copy2(wc, backup_dir / "chapter_word_counts.json")
    queue = []
    try:
        q = a.load_chapter_release_queue()
        queue = [x for x in q.get("assignments", []) if isinstance(x, dict) and str(x.get("key")) == f"{abbr}-{number}"]
    except Exception:
        pass
    manifest = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "root": str(root), "abbr": abbr, "number": number, "docs": meta,
                "docs_backup_file": docs_name, "docs_backup_sha256": sha256(raw), "docs_backup_bytes": len(raw),
                "old_folder": str(old_folder) if old_folder else None, "continuity_file": cont_name, "ledger_before": ledger_entry,
                "queue_assignments": queue, "ledger_added_keys": [], "docs_after_blob_sha": None, "new_folder": None}
    write_json(backup_dir / "manifest.json", manifest)
    (backup_dir / "restore.py").write_text(RESTORE_PY, encoding="utf-8")
    (backup_dir / "restore.ps1").write_text(
        f'Set-Location "{root}"\r\n& "{root}\\.venv-gpu\\Scripts\\python.exe" "{backup_dir}\\restore.py" @args\r\n', encoding="utf-8")
    return manifest


# ----------------------------------------------------------------------------- the operation
def run(abbr: str, number: int, draft_path: Path, *, apply: bool, backup_dir: Optional[Path] = None, app_mod=None, root: Path = ROOT,
        allow_posted: bool = False, resume: bool = False, report: Callable[[str], None] = print) -> dict[str, Any]:
    a = app_mod or load_app()
    abbr = a.story_key(abbr)
    if not abbr or abbr not in a.DOCS_NOVEL_FILES:
        raise ReplaceError("unknown novel")
    if apply and not os.environ.get("GITHUB_TOKEN", "").strip():
        raise ReplaceError("GITHUB_TOKEN not available (not printing it); stopping before any change")
    result: dict[str, Any] = {"abbr": abbr, "number": number, "apply": apply}
    # draft -> title/body exactly as the importer parses it
    raw_draft = Path(draft_path).read_text(encoding="utf-8")
    title, body = a.parse_manual_chapter_output(raw_draft, f"Chapter {number}")
    info = a.chapter_heading_info(title)
    if not info or info[0] != number:
        raise ReplaceError(f"draft heading {title!r} is not chapter {number}")
    result.update(title=title, draft_sha256=sha256(raw_draft))
    entry = a.chapter_ledger_entry(abbr, number) or {}
    posted = [k for k in POSTED_KEYS if entry.get(k)]
    result["ledger_posted_flags"] = posted
    if posted and not allow_posted:
        raise ReplaceError(f"ledger shows {abbr}-{number} already posted/prepared ({posted}); a live swap is out of scope")
    repo_path = a.DOCS_NOVEL_FILES[abbr]
    backup_dir = Path(backup_dir or root / "backups" / f"{abbr.lower()}{number}-replace-{time.strftime('%Y-%m-%d')}")
    manifest: dict[str, Any] = {}
    if resume:
        # finish the local steps after an interrupted run: Docs must already hold exactly the spliced text; nothing is re-uploaded
        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        meta = manifest["docs"]
        raw = (backup_dir / manifest["docs_backup_file"]).read_bytes()
    else:
        meta = github_meta(a, repo_path)
        raw = fetch_docs_bytes(a, repo_path)
    result["docs_before"] = {"blob_sha": meta["blob_sha"], "last_commit_sha": meta["last_commit_sha"], "sha256": sha256(raw), "bytes": len(raw)}
    before = chapters_from_bytes(a, abbr, raw)
    old = before["chapters"].get(number)
    if not old:
        raise ReplaceError(f"chapter {number} is not in the Docs file; use the normal import")
    result["old_chapter"] = {"heading": old["heading"], "words": count_words(old["raw_text"]), "sha_raw": old["sha_raw"]}
    new_raw, span = splice_docx(raw, number, title, body, heading_info=a.chapter_heading_info, paragraph_xml=a.docx_paragraph_xml)
    result["splice"] = {k: v for k, v in span.items() if k not in ("start", "end")}
    if abs(span["removed_words"] - result["old_chapter"]["words"]) > 15:
        raise ReplaceError(f"removed span words {span['removed_words']} != old chapter words {result['old_chapter']['words']}; refusing")
    after = chapters_from_bytes(a, abbr, new_raw)
    errs = compare_other_chapters(before, after, number)
    new_ch = after["chapters"].get(number) or {}
    errs += docs_body_matches_draft(new_ch.get("raw_text") or "", new_ch.get("heading") or title, body)
    result["others_checked"] = len(before["chapters"]) - 1
    result["new_chapter"] = {"heading": new_ch.get("heading"), "words": count_words(new_ch.get("raw_text") or "")}
    result["errors"] = errs
    result["new_docs_sha256"] = sha256(new_raw)
    if errs:
        raise ReplaceError("verification failed: " + "; ".join(errs))
    old_snips = [p.strip()[:80] for p in (old["raw_text"] or "").split("\n\n")[1:6] if len(p.strip()) > 60]
    jobs = release_job_report(root / "automation_state.db", abbr, number, old_snips, new_ch.get("heading") or title) if (root / "automation_state.db").exists() else []
    result["release_jobs"] = jobs
    report(f"verified in memory: other chapters identical ({result['others_checked']}), new words {result['new_chapter']['words']} (old {result['old_chapter']['words']})")
    if not apply:
        result["note"] = "dry run: nothing written"
        return result

    # ---- apply
    old_folder = Path(manifest["old_folder"]) if resume and manifest.get("old_folder") else (Path(entry["chapterFolder"]) if entry.get("chapterFolder") else None)
    result["backup_dir"] = str(backup_dir)
    if resume:
        if fetch_docs_bytes(a, repo_path) != new_raw:
            raise ReplaceError("resume: Docs does not hold exactly the spliced text; stopping")
        now_meta = github_meta(a, repo_path)
        up = {"path": repo_path, "sha": now_meta["blob_sha"], "commit": now_meta["last_commit_sha"], "resumed": True}
        report("resume: Docs already holds the spliced text; skipping backup and upload")
    else:
        manifest = make_backup(a, backup_dir, abbr, number, raw, meta, old_folder, entry, root)
        report(f"backup written: {backup_dir}")
        cur_blob = a.github_existing_sha(a.DOCS_REPO_OWNER, a.DOCS_REPO_NAME, repo_path, docs_branch())
        if cur_blob != meta["blob_sha"]:
            raise ReplaceError("Docs file changed between backup and upload; nothing uploaded")
        up = a.upload_bytes_to_github(new_raw, repo_path, f"Replace {a.NOVEL_NAMES.get(abbr, abbr)} {title}", owner=a.DOCS_REPO_OWNER, repo=a.DOCS_REPO_NAME, branch=docs_branch())
    commit_sha = up.get("commit") if isinstance(up.get("commit"), str) else ((up.get("commit") or {}).get("sha") if isinstance(up.get("commit"), dict) else None)
    content_sha = up.get("sha") if isinstance(up.get("sha"), str) else None
    result["docs_upload"] = {"commit": commit_sha, "blob_sha": content_sha}
    manifest["docs_after_blob_sha"] = content_sha
    write_json(backup_dir / "manifest.json", manifest)
    report(f"Docs commit {str(commit_sha)[:10]}")
    back = fetch_docs_bytes(a, repo_path)
    rb_errs = []
    if back != new_raw:
        rb_errs.append("remote bytes differ from the spliced file")
    cur = chapters_from_bytes(a, abbr, back)
    rb_errs += compare_other_chapters(before, cur, number)
    result["readback_errors"] = rb_errs
    if rb_errs:
        raise ReplaceError("read-back verification failed AFTER upload: " + "; ".join(rb_errs) + f" -> restore with {backup_dir}\\restore.ps1")
    docs_ch = cur["chapters"][number]
    # word count: same counter as the other saved counts, on the text exactly as it sits in Docs
    import chapter_word_counts

    lines = [ln for ln in docs_ch["raw_text"].split("\n\n")]
    docs_title = lines[0].strip()
    docs_body = "\n\n".join(lines[1:])
    wc = chapter_word_counts.record_import(abbr, docs_title, docs_body, {"commit": {"sha": commit_sha or ""}}, root / "chapter_word_counts.json")
    expected = count_words(docs_ch["raw_text"])
    result["word_count"] = {"saved": wc["words"], "docs_raw_text_words": expected, "draft_body_words": count_words(body), "draft_title_words": count_words(title)}
    if wc["words"] != expected:
        raise ReplaceError(f"saved word count {wc['words']} != Docs text count {expected}")
    # new chapter folder, like import_manual_written_chapter (old folder untouched)
    summary = a.summarize_chapter_for_snapshot(body)
    setup = a.next_setup_from_chapter_text(body)
    novel_name = a.NOVEL_NAMES.get(abbr, abbr)
    folder = a.CHAPTER_OUTPUT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{a.slugify(novel_name)}-chapter-{a.slugify(str(number))}-manual"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "chapter.txt").write_text(f"{title}\n\n{body.strip()}\n", encoding="utf-8")
    (folder / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    (folder / "continuity-notes.txt").write_text(setup + "\n", encoding="utf-8")
    write_json(folder / "metadata.json", {
        "title": title, "abbr": abbr, "novel": novel_name, "chapter_number": number, "chapter_text": body, "short_summary": summary,
        "continuity_notes": setup, "folder": str(folder), "chapter_file": str(folder / "chapter.txt"), "campaign": None,
        "github_docs_upload": {"upload": up, "file": repo_path, "branch": docs_branch(), "wordCount": wc}, "github_docs_warning": "",
        "source": "manual_chatgpt_replace", "replaces_folder": str(old_folder) if old_folder else None})
    manifest["new_folder"] = str(folder)
    # ledger: same fields as the Nov 10 imports; keep every posting flag untouched
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    updates = {"title": title, "written": True, "writePending": False, "writeMode": "manual_chatgpt", "writtenAt": now,
               "uploadedToGitHubDocs": True, "githubDocsUploaded": True, "githubDocsWarning": "",
               "promoPackBuilt": False, "promoBuilt": False, "chapterFolder": str(folder), "campaignFolder": "",
               "folders": {"chapter": str(folder), "campaign": ""},
               "replacedAt": now, "replacedFolder": str(old_folder) if old_folder else "",
               "replacedCampaignFolder": str(entry.get("campaignFolder") or ""), "replacedDocsCommit": commit_sha or ""}
    manifest["ledger_added_keys"] = [k for k in updates if k not in entry]
    write_json(backup_dir / "manifest.json", manifest)
    led = a.update_chapter_ledger(abbr, number, updates)
    result["ledger_after"] = {k: led.get(k) for k in ("written", "writeMode", "githubDocsUploaded", "promoBuilt", "chapterFolder", *POSTED_KEYS)}
    # continuity: replace ONLY this chapter's recent_chapters entry; never move last_chapter
    snap = a.load_continuity_snapshot(abbr)
    last_before = snap.get("last_chapter")
    new_snap, hit = continuity_replace_recent(snap, number, title, summary)
    if hit:
        a.save_continuity_snapshot(abbr, new_snap)
    after_snap = a.load_continuity_snapshot(abbr)
    result["continuity"] = {"entry_replaced": hit, "last_chapter_before": last_before, "last_chapter_after": after_snap.get("last_chapter")}
    if after_snap.get("last_chapter") != last_before:
        raise ReplaceError("continuity last_chapter moved; restore from backup")
    result["new_folder"] = str(folder)
    return result


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("abbr")
    ap.add_argument("number", type=int)
    ap.add_argument("draft")
    ap.add_argument("--apply", action="store_true", help="actually back up, upload and update local state (default: dry run)")
    ap.add_argument("--backup-dir")
    ap.add_argument("--allow-posted", action="store_true")
    ap.add_argument("--resume", action="store_true", help="finish local steps after an interrupted --apply (Docs already replaced)")
    args = ap.parse_args(argv)
    try:
        res = run(args.abbr, args.number, Path(args.draft), apply=args.apply, backup_dir=Path(args.backup_dir) if args.backup_dir else None, allow_posted=args.allow_posted, resume=args.resume)
    except ReplaceError as exc:
        print("STOP:", exc)
        return 2
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())