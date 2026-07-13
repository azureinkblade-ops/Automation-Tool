import datetime as dt
import json

import release_planner


def _chapter_index(*numbers):
    return [
        {
            "number": number,
            "title": f"Chapter {number}",
            "path": f"docs/chapter-{number}.md",
        }
        for number in numbers
    ]


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def test_weekday_plan_dates():
    request = release_planner.ReleasePlanRequest.from_payload(
        {
            "novel": "EN",
            "releaseThroughChapter": 22,
            "startChapter": 18,
            "firstInnerDiscipleDate": "2026-07-22",
            "weekdayOnly": True,
            "dryRun": True,
        }
    )
    rows, warnings = release_planner.build_release_plan_rows(
        request,
        novel_names={"EN": "Eternal Nexus"},
        chapter_indexes={"EN": _chapter_index(18, 19, 20, 21, 22)},
        current_upload_chapters={"EN": 18},
    )
    _assert(not warnings, f"unexpected warnings: {warnings}")
    _assert([row.chapter_number for row in rows] == [18, 19, 20, 21, 22], "wrong chapter order")
    _assert(rows[0].inner_disciple_date == "2026-07-22", "wrong first inner date")
    _assert(rows[0].path_initiate_date == "2026-07-29", "wrong first path date")
    _assert(rows[0].royal_road_date == "2026-08-05", "wrong first royal road date")
    _assert(rows[-1].inner_disciple_date == "2026-07-28", "weekday cursor did not skip weekend")
    _assert(all(dt.date.fromisoformat(row.inner_disciple_date).weekday() < 5 for row in rows), "weekend inner date found")


def test_missing_chapter_warning():
    request = release_planner.ReleasePlanRequest.from_payload(
        {
            "novel": "HA",
            "releaseThroughChapter": 20,
            "startChapter": 18,
            "firstInnerDiscipleDate": "2026-07-22",
        }
    )
    rows, warnings = release_planner.build_release_plan_rows(
        request,
        novel_names={"HA": "Heavenly Ascension System"},
        chapter_indexes={"HA": _chapter_index(18, 20)},
        current_upload_chapters={"HA": 18},
    )
    _assert([row.chapter_number for row in rows] == [18, 20], "existing rows missing")
    _assert(any(item.get("abbr") == "HA" and item.get("chapter") == 19 for item in warnings), "missing chapter warning not emitted")


def test_all_novel_current_paths():
    request = release_planner.ReleasePlanRequest.from_payload(
        {
            "novel": "ALL",
            "releaseThroughChapter": 19,
            "firstInnerDiscipleDate": "2026-07-22",
        }
    )
    rows, warnings = release_planner.build_release_plan_rows(
        request,
        novel_names={"EN": "Eternal Nexus", "HA": "Heavenly Ascension System"},
        chapter_indexes={
            "EN": _chapter_index(18, 19),
            "HA": _chapter_index(17, 18, 19),
        },
        current_upload_chapters={"EN": 18, "HA": 17},
    )
    keys = [row.key for row in rows]
    _assert(keys == ["EN-18", "HA-17", "EN-19", "HA-18", "HA-19"], f"unexpected all-novel order: {keys}")
    _assert(not warnings, f"unexpected warnings: {warnings}")


def test_due_targets_skip_prepared_and_posted():
    assignments = [
        {
            "key": "EN-18",
            "abbr": "EN",
            "chapter": 18,
            "innerDiscipleDate": "2026-07-22",
            "pathInitiateDate": "2026-07-29",
            "royalRoadDate": "2026-08-05",
            "innerPosted": False,
            "innerPrepared": False,
            "pathPosted": False,
            "pathPrepared": True,
            "royalRoadPosted": False,
            "royalRoadPrepared": False,
        },
        {
            "key": "HP-18",
            "abbr": "HP",
            "chapter": 18,
            "innerDiscipleDate": "2026-07-22",
            "pathInitiateDate": "2026-07-29",
            "royalRoadDate": "2026-08-05",
            "innerPosted": True,
            "innerPrepared": True,
            "pathPosted": False,
            "pathPrepared": False,
            "royalRoadPosted": False,
            "royalRoadPrepared": False,
        },
    ]
    targets = release_planner.release_stage_due_targets(assignments, today="2026-07-29")
    _assert(
        [(item["key"], item["stage"]) for item in targets] == [("EN-18", "inner_disciple"), ("HP-18", "path_initiate")],
        f"unexpected due targets: {targets}",
    )
    targets = release_planner.release_stage_due_targets(assignments, today="2026-07-29", include_prepared=True)
    _assert(
        [(item["key"], item["stage"]) for item in targets] == [("EN-18", "inner_disciple"), ("EN-18", "path_initiate"), ("HP-18", "path_initiate")],
        f"unexpected prepared-inclusive due targets: {targets}",
    )


def test_scheduled_targets_include_future_without_reopening_posted():
    assignments = [{
        "key": "EN-74",
        "abbr": "EN",
        "chapter": 74,
        "innerDiscipleDate": "2026-07-22",
        "pathInitiateDate": "2026-07-29",
        "royalRoadDate": "2026-08-05",
        "innerPosted": True,
        "pathPosted": False,
        "royalRoadPosted": False,
        "innerPrepared": True,
        "pathPrepared": False,
        "royalRoadPrepared": False,
    }]
    targets = release_planner.release_stage_due_targets(
        assignments,
        today="2026-07-12",
        include_scheduled=True,
    )
    _assert(
        [(item["key"], item["stage"], item["scheduled"]) for item in targets] == [
            ("EN-74", "path_initiate", True),
            ("EN-74", "royal_road", True),
        ],
        f"unexpected scheduled targets: {targets}",
    )


def main():
    tests = [
        test_weekday_plan_dates,
        test_missing_chapter_warning,
        test_all_novel_current_paths,
        test_due_targets_skip_prepared_and_posted,
        test_scheduled_targets_include_future_without_reopening_posted,
    ]
    results = []
    for test in tests:
        test()
        results.append({"test": test.__name__, "status": "passed"})
    print(json.dumps({"ok": True, "results": results}, indent=2))


if __name__ == "__main__":
    main()
