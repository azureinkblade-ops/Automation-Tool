"""CPU tests for tools/replace_written_chapter.py (fixtures only, no network, no real ledger/continuity/Docs)."""
from __future__ import annotations

import base64
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

import chapter_word_counts
from tools import replace_written_chapter as rwc

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SECT = '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>'


@pytest.fixture(scope="module")
def app_mod():
    import app as a

    a.wire_extracted_modules()
    return a


def _p(text: str, heading: bool = False) -> str:
    esc = text.replace("&", "&amp;").replace("<", "&lt;")
    if heading:
        return f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'
    return f'<w:p><w:r><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'


def _chapter_paras(n: int, tag: str = "old") -> list[str]:
    out = [_p(f"Chapter {n} - Title Number {n}", heading=True)]
    for i in range(6):
        out.append(_p(f"This is the {tag} paragraph {i} of chapter {n}. The lantern keeper walked the long road past the quiet river and counted the stars twice."))
    return out


def make_docx(chapters: dict[int, list[str]] | None = None, extra_body: str = "", sect: bool = True) -> bytes:
    chapters = chapters or {n: _chapter_paras(n) for n in range(1, 6)}
    body = "".join("".join(chapters[n]) for n in sorted(chapters)) + extra_body + (SECT if sect else "")
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/styles.xml", "<styles/>")
        z.writestr("word/document.xml", xml)
    return out.getvalue()


NEW_BODY = "\n\n".join(f"The new paragraph {i} says the keeper came at dark and stayed until the lamps were lit again." for i in range(7))
NEW_TITLE = "Chapter 3 - The Keeper Who Came at Dark"


def _bk(root):
    import time

    return root / "backups" / f"hp3-replace-{time.strftime('%Y-%m-%d')}"


def _splice(a, raw, n=3, title=NEW_TITLE, body=NEW_BODY):
    return rwc.splice_docx(raw, n, title, body, heading_info=a.chapter_heading_info, paragraph_xml=a.docx_paragraph_xml)


def test_insert_xml_is_the_same_markup_append_uses(app_mod):
    a = app_mod
    base = make_docx({1: _chapter_paras(1)})
    appended = a.append_chapter_to_docx(base, NEW_TITLE, NEW_BODY)
    with zipfile.ZipFile(io.BytesIO(base)) as z0, zipfile.ZipFile(io.BytesIO(appended)) as z1:
        x0, x1 = z0.read("word/document.xml").decode(), z1.read("word/document.xml").decode()
    inserted = x1[len(x0.split(SECT)[0]):x1.index(SECT)]
    mine, paragraphs = rwc.build_insert_xml(NEW_TITLE, NEW_BODY, a.docx_paragraph_xml)
    assert mine == inserted
    assert paragraphs[0] == NEW_TITLE and len(paragraphs) == 8


def test_splice_middle_chapter_only_changes_that_chapter(app_mod):
    a = app_mod
    raw = make_docx()
    new_raw, span = _splice(a, raw)
    before, after = rwc.chapters_from_bytes(a, "HP", raw), rwc.chapters_from_bytes(a, "HP", new_raw)
    assert rwc.compare_other_chapters(before, after, 3) == []
    assert before["numbers_in_order"] == after["numbers_in_order"] == [1, 2, 3, 4, 5]
    assert "the old paragraph" not in after["chapters"][3]["raw_text"]
    assert "the keeper came at dark" in after["chapters"][3]["raw_text"]
    assert span["removed_paragraphs"] == 7 and span["inserted_paragraphs"] == 8
    assert rwc.docs_body_matches_draft(after["chapters"][3]["raw_text"], NEW_TITLE, NEW_BODY) == []


def test_splice_last_chapter_keeps_section_properties(app_mod):
    a = app_mod
    raw = make_docx()
    new_raw, _ = _splice(a, raw, n=5, title="Chapter 5 - End", body=NEW_BODY)
    with zipfile.ZipFile(io.BytesIO(new_raw)) as z:
        xml = z.read("word/document.xml").decode()
    assert xml.endswith(SECT + "</w:body></w:document>")
    after = rwc.chapters_from_bytes(a, "HP", new_raw)
    assert after["numbers_in_order"] == [1, 2, 3, 4, 5] and "the keeper came at dark" in after["chapters"][5]["raw_text"]


def test_other_zip_members_and_outside_xml_are_byte_identical(app_mod):
    a = app_mod
    raw = make_docx()
    new_raw, span = _splice(a, raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z0, zipfile.ZipFile(io.BytesIO(new_raw)) as z1:
        assert z0.read("word/styles.xml") == z1.read("word/styles.xml")
        assert z0.read("[Content_Types].xml") == z1.read("[Content_Types].xml")
        x0, x1 = z0.read("word/document.xml").decode(), z1.read("word/document.xml").decode()
    assert x0[: span["start"]] == x1[: span["start"]]
    assert x0[span["end"]:] == x1[len(x1) - len(x0[span["end"]:]):]


def test_splice_refuses_unsafe_or_missing_targets(app_mod):
    a = app_mod
    with pytest.raises(rwc.ReplaceError, match="no heading paragraph for chapter 9"):
        _splice(a, make_docx(), n=9, title="Chapter 9 - X")
    with pytest.raises(rwc.ReplaceError, match="text boxes"):
        _splice(a, make_docx(extra_body="<w:p><w:r><w:pict><w:txbxContent><w:p/></w:txbxContent></w:pict></w:r></w:p>"))
    chapters = {n: _chapter_paras(n) for n in range(1, 6)}
    chapters[3] = chapters[3][:3] + ["<w:tbl><w:tr><w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"] + chapters[3][3:]
    with pytest.raises(rwc.ReplaceError, match="table"):
        _splice(a, make_docx(chapters))


def test_compare_detects_a_changed_neighbour(app_mod):
    a = app_mod
    raw = make_docx()
    chapters = {n: _chapter_paras(n) for n in range(1, 6)}
    chapters[4] = _chapter_paras(4, tag="tampered")
    bad = rwc.chapters_from_bytes(a, "HP", make_docx(chapters))
    good = rwc.chapters_from_bytes(a, "HP", raw)
    errs = rwc.compare_other_chapters(good, bad, 3)
    assert errs == ["chapter 4 text changed"]


def test_docs_body_matches_draft_flags_differences():
    heading = "Chapter 3: T"
    raw = "Chapter 3 - T\n\nOne two three four five six."
    assert rwc.docs_body_matches_draft(raw, heading, "One two three four five six.") == []
    assert rwc.docs_body_matches_draft(raw, heading, "Totally different opening here and more words") != []
    long_draft = "One two three four five six. " + "word " * 40
    assert any("word count" in e for e in rwc.docs_body_matches_draft(raw, heading, long_draft))


def test_continuity_replace_never_moves_last_chapter():
    snap = {"last_chapter": 158, "last_title": "L", "next_chapter_setup": "S",
            "recent_chapters": [{"chapter": 154, "title": "old", "summary": "old s"}, {"chapter": 158, "title": "t158", "summary": "s158"}]}
    new, hit = rwc.continuity_replace_recent(snap, 154, "Chapter 154 - New", "new s")
    assert hit and new["last_chapter"] == 158 and new["last_title"] == "L" and new["next_chapter_setup"] == "S"
    assert new["recent_chapters"][0] == {"chapter": 154, "title": "Chapter 154 - New", "summary": "new s"}
    assert new["recent_chapters"][1]["title"] == "t158"
    assert snap["recent_chapters"][0]["title"] == "old"  # input untouched
    _, hit2 = rwc.continuity_replace_recent(snap, 150, "x", "y")
    assert hit2 is False


def test_release_job_report_flags_jobs_that_hold_text(tmp_path):
    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute("create table release_automation_jobs (job_id text, novel_abbr text, chapter_number int, stage text, status text, scheduled_for text, payload_json text, last_error text)")
    con.execute("insert into release_automation_jobs values ('j1','HP',154,'inner_disciple','blocked','2026-10-12',?,'')", (json.dumps({"title": "Chapter 154 - X", "chapter": 154}),))
    con.execute("insert into release_automation_jobs values ('j2','HP',154,'royal_road','blocked','2026-10-26',?,'')", (json.dumps({"title": "T", "chapterText": "old words " * 100}),))
    con.execute("insert into release_automation_jobs values ('j3','HP',155,'royal_road','pending','2026-10-26','{}','')")
    con.commit()
    con.close()
    rows = rwc.release_job_report(db, "HP", 154, ["old words old words"], "Chapter 154 - X")
    assert [r["job_id"] for r in rows] == ["j1", "j2"]
    assert rows[0]["holds_own_copy"] is False and rows[0]["payload_title_matches_new"] is True
    assert rows[1]["holds_own_copy"] is True and "chapterText" in rows[1]["long_text_fields"]


# ---------------------------------------------------------------- end to end with an in-memory "GitHub"
class FakeRemote:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.version = 1
        self.uploads = 0

    def api(self, method, path, payload=None):
        if "/commits?path=" in path:
            return [{"sha": f"commit{self.version}"}]
        if "/commits/" in path:
            return {"sha": f"head{self.version}"}
        if method == "GET" and "/contents/" in path:
            return {"content": base64.b64encode(self.raw).decode(), "sha": f"blob{self.version}", "size": len(self.raw)}
        raise AssertionError((method, path))

    def existing_sha(self, owner, repo, path, branch):
        return f"blob{self.version}"

    def upload(self, content, repo_path, message, *, owner, repo, branch=None):
        self.raw = content
        self.version += 1
        self.uploads += 1
        return {"path": repo_path, "sha": f"blob{self.version}", "commit": f"commit{self.version}", "html_url": ""}


@pytest.fixture()
def world(app_mod, tmp_path, monkeypatch):
    a = app_mod
    raw = make_docx()
    remote = FakeRemote(raw)
    ledger = {"title": "Chapter 3: Old", "written": True, "writeMode": "manual_chatgpt", "postedToPatreon": False, "postedToRoyalRoad": False,
              "patreonDraftPrepared": False, "chapterFolder": str(tmp_path / "chapters" / "old-folder"), "campaignFolder": "C:/old/campaign", "promoBuilt": True}
    old_folder = tmp_path / "chapters" / "old-folder"
    old_folder.mkdir(parents=True)
    (old_folder / "chapter.txt").write_text("OLD TEXT", encoding="utf-8")
    cont = {"last_chapter": 5, "last_title": "Chapter 5", "recent_chapters": [{"chapter": 3, "title": "old", "summary": "old"}, {"chapter": 5, "title": "t5", "summary": "s5"}]}
    (tmp_path / "continuity").mkdir()
    (tmp_path / "continuity" / "HP-summary.json").write_text(json.dumps(cont), encoding="utf-8")
    chapter_word_counts.record("HP", 3, 999, "seed", "abc", tmp_path / "chapter_word_counts.json")
    state = {"ledger": ledger, "cont": cont}

    def update(abbr, n, upd):
        state["ledger"].update(upd)
        return dict(state["ledger"])

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(a, "github_api_request", remote.api)
    monkeypatch.setattr(a, "github_existing_sha", remote.existing_sha)
    monkeypatch.setattr(a, "upload_bytes_to_github", remote.upload)
    monkeypatch.setattr(a, "chapter_ledger_entry", lambda abbr, n: dict(state["ledger"]))
    monkeypatch.setattr(a, "update_chapter_ledger", update)
    monkeypatch.setattr(a, "load_chapter_release_queue", lambda: {"assignments": [{"key": "HP-3", "title": "t"}]})
    monkeypatch.setattr(a, "load_continuity_snapshot", lambda abbr: dict(state["cont"]))
    monkeypatch.setattr(a, "save_continuity_snapshot", lambda abbr, d: state.__setitem__("cont", dict(d)))
    monkeypatch.setattr(a, "CHAPTER_OUTPUT_DIR", tmp_path / "chapters")
    draft = tmp_path / "HP-3.md"
    draft.write_text(NEW_TITLE + "\n\n" + NEW_BODY + "\n", encoding="utf-8")
    return a, remote, state, draft, tmp_path


def test_dry_run_writes_nothing(world):
    a, remote, state, draft, root = world
    res = rwc.run("HP", 3, draft, apply=False, app_mod=a, root=root, report=lambda m: None)
    assert res["errors"] == [] and res["note"].startswith("dry run")
    assert remote.uploads == 0 and not (root / "backups").exists()
    assert state["ledger"]["promoBuilt"] is True


def test_apply_end_to_end(world):
    a, remote, state, draft, root = world
    before_raw = remote.raw
    res = rwc.run("HP", 3, draft, apply=True, app_mod=a, root=root, report=lambda m: None)
    assert remote.uploads == 1 and remote.raw != before_raw
    bk = Path(res["backup_dir"])
    assert (bk / "The Hundredfold Path - Updated Revision.docx").read_bytes() == before_raw
    assert (bk / "restore.py").exists() and (bk / "restore.ps1").exists() and (bk / "chapter_word_counts.json").exists()
    assert (bk / "old-chapter-folder" / "old-folder" / "chapter.txt").read_text(encoding="utf-8") == "OLD TEXT"
    manifest = json.loads((bk / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["docs"]["blob_sha"] == "blob1" and manifest["docs_after_blob_sha"] == "blob2" and manifest["ledger_before"]["promoBuilt"] is True
    # new folder next to the old one; old folder untouched
    new_folder = Path(res["new_folder"])
    assert new_folder.name.endswith("hundredfold-path-chapter-3-manual") and (new_folder / "chapter.txt").read_text(encoding="utf-8").startswith(NEW_TITLE)
    assert (root / "chapters" / "old-folder" / "chapter.txt").read_text(encoding="utf-8") == "OLD TEXT"
    # ledger: same import fields, posting flags untouched, stale promo cleared but remembered
    led = state["ledger"]
    assert led["written"] is True and led["writeMode"] == "manual_chatgpt" and led["chapterFolder"] == str(new_folder)
    assert led["promoBuilt"] is False and led["replacedCampaignFolder"] == "C:/old/campaign" and led["postedToPatreon"] is False
    # continuity: only the chapter 3 entry changed, last_chapter not rolled back
    assert state["cont"]["last_chapter"] == 5 and state["cont"]["recent_chapters"][0]["title"] == NEW_TITLE
    assert state["cont"]["recent_chapters"][1] == {"chapter": 5, "title": "t5", "summary": "s5"}
    # saved word count = same counter on the Docs text (heading + body), old value kept under "previous"
    saved = chapter_word_counts.load(root / "chapter_word_counts.json")["chapters"]["HP-3"]
    docs_text = rwc.chapters_from_bytes(a, "HP", remote.raw)["chapters"][3]["raw_text"]
    assert saved["words"] == chapter_word_counts.words(docs_text) == res["word_count"]["saved"]
    assert saved["previous"][-1]["words"] == 999 and saved["docsCommit"] == "commit2"
    assert res["readback_errors"] == [] and res["others_checked"] == 4


def test_apply_refuses_posted_chapter_and_leaves_remote_alone(world):
    a, remote, state, draft, root = world
    state["ledger"]["postedToPatreon"] = True
    with pytest.raises(rwc.ReplaceError, match="already posted"):
        rwc.run("HP", 3, draft, apply=True, app_mod=a, root=root, report=lambda m: None)
    assert remote.uploads == 0 and not (root / "backups").exists()


def test_apply_refuses_wrong_chapter_number_in_draft(world):
    a, remote, state, draft, root = world
    draft.write_text("Chapter 9 - Wrong\n\nBody text here.\n", encoding="utf-8")
    with pytest.raises(rwc.ReplaceError, match="is not chapter 3"):
        rwc.run("HP", 3, draft, apply=True, app_mod=a, root=root, report=lambda m: None)
    assert remote.uploads == 0


def test_apply_requires_a_token_before_touching_anything(world, monkeypatch):
    a, remote, state, draft, root = world
    monkeypatch.setenv("GITHUB_TOKEN", "")
    with pytest.raises(rwc.ReplaceError, match="GITHUB_TOKEN"):
        rwc.run("HP", 3, draft, apply=True, app_mod=a, root=root, report=lambda m: None)
    assert remote.uploads == 0 and not (root / "backups").exists()


def test_refuses_to_overwrite_an_existing_backup(world):
    a, remote, state, draft, root = world
    rwc.run("HP", 3, draft, apply=True, app_mod=a, root=root, report=lambda m: None)
    with pytest.raises(rwc.ReplaceError, match="already exists"):
        rwc.run("HP", 3, draft, apply=True, app_mod=a, root=root, report=lambda m: None)
    assert remote.uploads == 1


def test_resume_finishes_local_steps_without_reuploading(world):
    a, remote, state, draft, root = world
    # simulate an interrupted run: backup + upload done, local steps not
    raw = remote.raw
    new_raw, _ = _splice(a, raw)
    manifest = rwc.make_backup(a, _bk(root), "HP", 3, raw,
                               rwc.github_meta(a, a.DOCS_NOVEL_FILES["HP"]), root / "chapters" / "old-folder", dict(state["ledger"]), root)
    remote.upload(new_raw, a.DOCS_NOVEL_FILES["HP"], "m", owner="o", repo="r")
    res = rwc.run("HP", 3, draft, apply=True, resume=True, app_mod=a, root=root, report=lambda m: None)
    assert remote.uploads == 1  # only the simulated one
    assert state["ledger"]["promoBuilt"] is False and state["cont"]["last_chapter"] == 5
    assert res["docs_upload"]["commit"] == "commit2" and manifest["docs"]["blob_sha"] == "blob1"


def test_resume_refuses_when_docs_do_not_match(world):
    a, remote, state, draft, root = world
    rwc.make_backup(a, _bk(root), "HP", 3, remote.raw,
                    rwc.github_meta(a, a.DOCS_NOVEL_FILES["HP"]), None, dict(state["ledger"]), root)
    with pytest.raises(rwc.ReplaceError, match="resume"):
        rwc.run("HP", 3, draft, apply=True, resume=True, app_mod=a, root=root, report=lambda m: None)
    assert state["ledger"]["promoBuilt"] is True