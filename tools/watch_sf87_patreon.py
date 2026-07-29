"""Focused watcher: alert the moment SF chapter 87 reaches the Patreon draft/post stage.
Polls patreon-draft-pending.json + post-records.json every 10s.
Prints a clear marker line when detected, then keeps watching for the post-record too.
Non-fatal; just a sentinel. Stop by killing the process.
"""
import json, os, time, sys

REPO = r"C:\Users\David\Documents\Automation tool"
os.chdir(REPO)
SEEN_DRAFT = False
SEEN_POST = False


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def patreon_draft_is_sf87():
    d = load_json("patreon-draft-pending.json")
    if not d:
        return False
    nov = str(d.get("novel", "")).upper()
    ch = str(d.get("chapter", ""))
    return nov == "SF" and ch == "87"


def post_record_sf87_patreon():
    recs = load_json("post-records.json")
    if isinstance(recs, dict):
        recs = recs.get("records", recs)
    for v in recs.values():
        if str(v.get("novel", "")).upper() == "SF" and str(v.get("chapter", "")) == "87" \
           and str(v.get("platform", "")).lower() == "patreon":
            return v
    return None


def main() -> None:
    global SEEN_DRAFT, SEEN_POST
    print("SF87-PATREON-WATCHER START (polling every 10s)", flush=True)
    while True:
        if not SEEN_DRAFT and patreon_draft_is_sf87():
            SEEN_DRAFT = True
            print(">>> SF 87 PATREON DRAFT CREATED (patreon-draft-pending.json now points to SF 87) <<<", flush=True)
        if not SEEN_POST and post_record_sf87_patreon():
            SEEN_POST = True
            print(">>> SF 87 PATREON POST RECORD WRITTEN (post-records.json) <<<", flush=True)
        if SEEN_DRAFT and SEEN_POST:
            print("SF87-PATREON-WATCHER DONE (both draft + post record confirmed)", flush=True)
            break
        time.sleep(10)


if __name__ == "__main__":
    main()
