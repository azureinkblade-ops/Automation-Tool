"""Focused watcher: alert when the NEXT EN chapter (any EN chapter > 80) reaches Patreon.
After SF 88 fired, EN is next in the four-lane rotation; the next EN chapter is 81+.
Polls patreon-draft-pending.json + post-records.json every 10s.
Prints a clear marker when detected, then keeps watching for the post-record too.
"""
import json, os, time

REPO = r"C:\Users\David\Documents\Automation tool"
os.chdir(REPO)
SEEN_DRAFT = False
SEEN_POST = False
MIN_CH = 87  # EN next upload is around ch 87/88 (scheduler catching up), not sequential from 80


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def draft_is_next_en():
    d = load_json("patreon-draft-pending.json")
    if not d:
        return None
    nov = str(d.get("novel", "")).upper()
    try:
        ch = int(d.get("chapter", 0))
    except Exception:
        ch = 0
    if nov == "EN" and ch >= MIN_CH:
        return ch
    return None


def post_record_next_en():
    recs = load_json("post-records.json")
    if isinstance(recs, dict):
        recs = recs.get("records", recs)
    best = None
    for v in recs.values():
        if str(v.get("novel", "")).upper() == "EN" and str(v.get("platform", "")).lower() == "patreon":
            try:
                ch = int(v.get("chapter", 0))
            except Exception:
                ch = 0
            if ch >= MIN_CH and (best is None or ch > best):
                best = ch
    return best


def main() -> None:
    global SEEN_DRAFT, SEEN_POST
    last_draft_ch = 0
    last_post_ch = 0
    print(f"EN-NEXT-PATREON-WATCHER START (watching EN ch>={MIN_CH}, polling 10s, durable)", flush=True)
    while True:
        ch = draft_is_next_en()
        if ch and ch != last_draft_ch:
            last_draft_ch = ch
            print(f">>> EN {ch} PATREON DRAFT CREATED (patreon-draft-pending.json now points to EN {ch}) <<<", flush=True)
        pc = post_record_next_en()
        if pc and pc != last_post_ch:
            last_post_ch = pc
            print(f">>> EN {pc} PATREON POST RECORD WRITTEN (post-records.json) <<<", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
