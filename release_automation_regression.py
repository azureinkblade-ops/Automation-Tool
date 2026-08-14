from __future__ import annotations

import tempfile
from pathlib import Path

import automation_db


def test_release_jobs_are_idempotent() -> None:
    root = Path(tempfile.mkdtemp())
    job = {"abbr": "EN", "chapter": 74, "stage": "inner_disciple", "date": "2026-07-22"}
    first = automation_db.enqueue_release_jobs(root, [job])
    second = automation_db.enqueue_release_jobs(root, [job])
    assert first == {"inserted": 1, "existing": 0}
    assert second == {"inserted": 0, "existing": 1}


def test_release_jobs_claim_in_release_order() -> None:
    root = Path(tempfile.mkdtemp())
    automation_db.enqueue_release_jobs(root, [
        {"abbr": "EN", "chapter": 74, "stage": "royal_road", "date": "2026-08-05"},
        {"abbr": "EN", "chapter": 74, "stage": "path_initiate", "date": "2026-07-29"},
        {"abbr": "EN", "chapter": 74, "stage": "inner_disciple", "date": "2026-07-22"},
    ])
    claimed = automation_db.claim_next_release_job(root, "regression")
    assert claimed is not None
    assert claimed["stage"] == "inner_disciple"
    assert claimed["status"] == "running"
    assert claimed["attemptCount"] == 1


def test_release_job_completion_is_persistent() -> None:
    root = Path(tempfile.mkdtemp())
    automation_db.enqueue_release_jobs(root, [
        {"abbr": "HA", "chapter": 63, "stage": "royal_road", "date": "2026-08-05"},
    ])
    claimed = automation_db.claim_next_release_job(root, "regression")
    assert claimed is not None
    updated = automation_db.update_release_job(
        root,
        claimed["jobId"],
        "verified",
        remoteUrl="https://example.invalid/chapter/63",
    )
    assert updated is not None
    assert updated["status"] == "verified"
    assert updated["verifiedAt"]
    assert updated["remoteUrl"].endswith("/63")
    assert automation_db.claim_next_release_job(root, "regression") is None


def test_release_job_prerequisites_block_later_stages() -> None:
    root = Path(tempfile.mkdtemp())
    automation_db.enqueue_release_jobs(root, [
        {"abbr": "SF", "chapter": 81, "stage": "inner_disciple", "date": "2026-07-21"},
        {"abbr": "SF", "chapter": 81, "stage": "path_initiate", "date": "2026-07-28"},
        {"abbr": "SF", "chapter": 81, "stage": "royal_road", "date": "2026-08-04"},
    ])
    inner = automation_db.claim_next_release_job(root, "regression")
    assert inner and inner["stage"] == "inner_disciple"
    assert automation_db.claim_next_release_job(root, "second-worker") is None
    automation_db.update_release_job(root, inner["jobId"], "verified")
    path = automation_db.claim_next_release_job(root, "regression")
    assert path and path["stage"] == "path_initiate"
    assert automation_db.claim_next_release_job(root, "second-worker") is None
    automation_db.update_release_job(root, path["jobId"], "verified")
    royal_road = automation_db.claim_next_release_job(root, "regression")
    assert royal_road and royal_road["stage"] == "royal_road"


def test_retrying_chapter_blocks_later_chapter_in_same_novel_stage() -> None:
    root = Path(tempfile.mkdtemp())
    automation_db.enqueue_release_jobs(root, [
        {"abbr": "HA", "chapter": 84, "stage": "inner_disciple", "date": "2026-08-20"},
        {"abbr": "HA", "chapter": 85, "stage": "inner_disciple", "date": "2026-08-21"},
    ])
    earlier = automation_db.claim_next_release_job(root, "regression")
    assert earlier and earlier["chapter"] == 84
    automation_db.update_release_job(
        root,
        earlier["jobId"],
        "retrying",
        nextAttemptAt="2999-01-01 00:00:00",
        lastError="transient failure",
    )
    assert automation_db.claim_next_release_job(root, "second-worker") is None


def test_retrying_chapter_does_not_block_another_novel() -> None:
    root = Path(tempfile.mkdtemp())
    automation_db.enqueue_release_jobs(root, [
        {"abbr": "HA", "chapter": 84, "stage": "inner_disciple", "date": "2026-08-20"},
        {"abbr": "HA", "chapter": 85, "stage": "inner_disciple", "date": "2026-08-21"},
        {"abbr": "EN", "chapter": 130, "stage": "inner_disciple", "date": "2026-08-22"},
    ])
    earlier = automation_db.claim_next_release_job(root, "regression")
    assert earlier and earlier["abbr"] == "HA" and earlier["chapter"] == 84
    automation_db.update_release_job(
        root,
        earlier["jobId"],
        "retrying",
        nextAttemptAt="2999-01-01 00:00:00",
        lastError="transient failure",
    )
    unrelated = automation_db.claim_next_release_job(root, "second-worker")
    assert unrelated and unrelated["abbr"] == "EN" and unrelated["chapter"] == 130


def test_release_job_payload_updates_preserve_identity() -> None:
    root = Path(tempfile.mkdtemp())
    automation_db.enqueue_release_jobs(root, [
        {"abbr": "HP", "chapter": 94, "stage": "royal_road", "date": "2026-08-04"},
    ])
    job = automation_db.claim_next_release_job(root, "regression")
    assert job
    updated = automation_db.update_release_job(
        root,
        job["jobId"],
        "blocked",
        payloadUpdates={
            "editUrl": "https://www.royalroad.com/author-dashboard/chapters/editdraft/123",
            "resultPath": "C:/tmp/result.json",
        },
        lastError="review required",
    )
    assert updated
    assert updated["jobId"] == job["jobId"]
    assert updated["editUrl"].endswith("/123")
    assert updated["resultPath"].endswith("result.json")
    assert updated["lastError"] == "review required"


def test_systemic_failure_reset_restores_pending_job() -> None:
    root = Path(tempfile.mkdtemp())
    automation_db.enqueue_release_jobs(root, [
        {"abbr": "EN", "chapter": 75, "stage": "inner_disciple", "date": "2026-07-23"},
    ])
    job = automation_db.claim_next_release_job(root, "regression")
    assert job
    automation_db.update_release_job(
        root,
        job["jobId"],
        "retrying",
        lastError="network failed with WinError 10013",
    )
    assert automation_db.reset_release_jobs_after_systemic_failure(root, "WinError 10013") == 1
    reset = automation_db.list_release_jobs(root)[0]
    assert reset["status"] == "pending"
    assert reset["attemptCount"] == 0
    assert reset["lastError"] == ""


def main() -> None:
    tests = [
        test_release_jobs_are_idempotent,
        test_release_jobs_claim_in_release_order,
        test_release_job_completion_is_persistent,
        test_release_job_prerequisites_block_later_stages,
        test_retrying_chapter_blocks_later_chapter_in_same_novel_stage,
        test_retrying_chapter_does_not_block_another_novel,
        test_release_job_payload_updates_preserve_identity,
        test_systemic_failure_reset_restores_pending_job,
    ]
    for test in tests:
        test()
    print(f"release automation regression: {len(tests)} passed")


if __name__ == "__main__":
    main()
