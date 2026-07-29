"""Process/state tracker for the Automation Tool app (PID 19964 on :8765).
Polls every 8s and logs DELTAS only (process mem, port listener, key state files).
Run as tracked background. Read logs/process_tracker.log to follow along.
"""
import os, time, json, subprocess, datetime

APP_PID = 19964
PORT = 8765
REPO = r"C:\Users\David\Documents\Automation tool"
STATE_FILES = [
    "automation_state.db", "automation_state.db-wal",
    "chapter_ledger.json", "post-records.json", "clickup-sync.json",
    "release_status.json", "image-feedback.json", "patreon-draft-pending.json",
    "chapter-path-state.json",
]
LOG = os.path.join(REPO, "logs", "process_tracker.log")

def now():
    return datetime.datetime.now().strftime("%H:%M:%S")

def port_listening():
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f":{PORT}" in line and "LISTENING" in line:
            return True
    return False

def proc_mem(pid):
    out = subprocess.run(["tasklist", "/nh", "/fo", "csv"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f'"{pid}"' in line or f",{pid}," in line:
            # CSV: "Image","PID","Session","Session#","Mem"
            try:
                return line.split(",")[4].strip().strip('"')
            except Exception:
                return "?"
    return "GONE"

def file_state():
    s = {}
    for f in STATE_FILES:
        p = os.path.join(REPO, f)
        if os.path.exists(p):
            st = os.stat(p)
            s[f] = (st.st_size, int(st.st_mtime))
    return s

def post_events():
    """Read post-records.json + patreon draft; return (records_dict, events_list).
    records_dict keyed by record key for delta detection; events_list of human lines."""
    events = []
    recs = {}
    pr = os.path.join(REPO, "post-records.json")
    if os.path.exists(pr):
        try:
            data = json.load(open(pr, encoding="utf-8"))
            recs = data.get("records", {})
        except Exception:
            pass
    # patreon draft
    pd = os.path.join(REPO, "patreon-draft-pending.json")
    if os.path.exists(pd):
        try:
            d = json.load(open(pd, encoding="utf-8"))
            title = d.get("title", "?")
            pd_at = d.get("created_at", "")
            events.append(f"PATREON draft: {title} (created {pd_at})")
        except Exception:
            pass
    return recs, events

def main():
    prev = {"mem": None, "port": None, "files": None, "posts": None, "patreon": None}
    print(f"[{now()}] TRACKER START pid={APP_PID} port={PORT}", flush=True)
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"[{now()}] TRACKER START pid={APP_PID} port={PORT}\n")
        while True:
            ts = now()
            mem = proc_mem(APP_PID)
            port = port_listening()
            fs = file_state()
            changed = []
            if mem != prev["mem"]:
                changed.append(f"mem {prev['mem']}->{mem}")
                prev["mem"] = mem
            if port != prev["port"]:
                changed.append(f"port_listen {prev['port']}->{port}")
                prev["port"] = port
            if prev["files"] is None:
                prev["files"] = fs
                changed.append("files baseline captured")
            else:
                for f, (sz, mt) in fs.items():
                    if f not in prev["files"]:
                        changed.append(f"{f} NEW")
                    elif prev["files"][f] != (sz, mt):
                        old = prev["files"][f]
                        changed.append(f"{f} size {old[0]}->{sz} mtime-changed")
                prev["files"] = fs
            # ---- post/platform events (X, Facebook, Buffer, Patreon, etc.) ----
            recs, pevents = post_events()
            if prev["posts"] is None:
                prev["posts"] = set(recs.keys())
            else:
                new_keys = set(recs.keys()) - prev["posts"]
                for k in new_keys:
                    r = recs[k]
                    plat = (r.get("platform") or "?").upper()
                    nov = r.get("novel", "?")
                    ch = r.get("chapter", "?")
                    buf = " buffer" if r.get("bufferPostId") else ""
                    changed.append(f"POST -> {plat}{buf} | {nov} ch{ch} | {k}")
                prev["posts"] = set(recs.keys())
            # patreon draft (emit once when it appears/changes)
            pdraft = None
            pd_path = os.path.join(REPO, "patreon-draft-pending.json")
            if os.path.exists(pd_path):
                try:
                    pdraft = json.load(open(pd_path, encoding="utf-8")).get("created_at")
                except Exception:
                    pdraft = None
            if pdraft != prev["patreon"]:
                if pdraft:
                    for ev in pevents:
                        if ev.startswith("PATREON"):
                            changed.append(ev)
                prev["patreon"] = pdraft
            # ----------------------------------------------------------------
            if changed:
                line = f"[{ts}] " + " | ".join(changed)
                print(line, flush=True)
                log.write(line + "\n")
            time.sleep(8)

if __name__ == "__main__":
    main()
