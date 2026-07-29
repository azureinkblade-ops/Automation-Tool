"""Release tracker — shows Patreon/Royal Road stages that are DUE or upcoming.
Cuts through the 3-stage stagger (Inner Disciple / Path Initiate +7d / Royal Road +14d) so you can
see per-DATE what needs to go out, instead of scanning a flat Patreon Library.

Usage:
  release_tracker.py            # due now + next 14 days, grouped by date
  release_tracker.py 30         # look ahead 30 days
  release_tracker.py --overdue  # only stages already due but not done
"""
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = r"C:\Users\David\Documents\Automation tool"
TODAY = date(2026, 7, 14)  # date anchor; change if system clock differs
STAGES = [
    ("Inner Disciple", "patreonInnerDisciplePosted", "innerDiscipleDate"),
    ("Path Initiate", "patreonPathInitiatePosted", "pathInitiateDate"),
    ("Royal Road", "royalRoadExists", "royalRoadDate"),
]


ROOT_PATH = Path(ROOT)
sys.path.insert(0, str(ROOT_PATH))

import automation_db  # noqa: E402


def load_release_status_from_db():
    try:
        data = automation_db.load_release_status(ROOT_PATH)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse(d):
    try:
        return date.fromisoformat(str(d))
    except Exception:
        return None


def main():
    horizon = 14
    overdue_only = False
    min_ch = 0
    for arg in sys.argv[1:]:
        if arg == "--overdue":
            overdue_only = True
        elif arg.startswith("--min="):
            min_ch = int(arg.split("=", 1)[1])
        elif arg.isdigit():
            horizon = int(arg)

    rs = load_release_status_from_db()
    chapters = rs.get("chapters", {})
    cutoff = TODAY + timedelta(days=horizon)

    # collect due/upcoming stage events
    events = []  # (date, novel, chapter, stage, status)
    for v in chapters.values():
        ab = v.get("abbr")
        ch = v.get("chapter")
        if not ab or not isinstance(ch, int):
            continue
        for label, done_key, date_key in STAGES:
            done = bool(v.get(done_key))
            d = parse(v.get(date_key))
            if done or d is None:
                continue
            if overdue_only:
                if d <= TODAY:
                    events.append((d, ab, ch, label, "OVERDUE"))
            else:
                if d <= cutoff:
                    status = "DUE" if d <= TODAY else "upcoming"
                    events.append((d, ab, ch, label, status))

    events.sort(key=lambda e: (e[0], e[1], e[2]))

    if not events:
        print(f"Nothing {'overdue' if overdue_only else f'due within {horizon} days'}. All caught up.")
        return

    title = "OVERDUE stages" if overdue_only else f"Release stages due within {horizon} days (as of {TODAY})"
    print(f"=== {title} ===\n")
    cur_date = None
    for d, ab, ch, label, status in events:
        if d != cur_date:
            cur_date = d
            weekday = d.strftime("%a")
            marker = "  <-- TODAY" if d == TODAY else (" (past due)" if d < TODAY else "")
            print(f"\n{d} {weekday}{marker}")
        flag = "!!" if status in ("DUE", "OVERDUE") else "  "
        print(f"   {flag} {ab} Ch {ch:<4} {label}")

    # summary
    due = sum(1 for e in events if e[4] in ("DUE", "OVERDUE"))
    print(f"\n{len(events)} stage(s) total | {due} due/overdue now")


if __name__ == "__main__":
    main()
