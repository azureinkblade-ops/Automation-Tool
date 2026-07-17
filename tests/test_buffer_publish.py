"""Characterization tests for buffer_publish + browser_publish (Task 6 extraction).

Required regression contracts (from the plan):
- buffer_post_from_folder(folder, ["c1"], "tiktok", "addToQueue") returns {"posts":[...]}.
- Instagram post vs reel type preserved in routing (instagram image -> "post";
  instagram reel video -> "reel").
- configured_buffer_channels() routing matches app.py.
- publish_x_post returns a post response; text is taken verbatim (matches app.py).
- manual_facebook_assist returns the FB result and uses an injectable browser launcher
  (no real OS launch in test).

Run: python tests/test_buffer_publish.py   (from repo root)
"""
import os, sys, tempfile, json
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import app as app_mod
import buffer_publish as bp
import browser_publish as br

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- configured_buffer_channels matches app.py (pure routing) ---
app_channels = app_mod.configured_buffer_channels()
bp_channels = bp.configured_buffer_channels()
check("configured_buffer_channels matches app.py", bp_channels, app_channels)

# --- build a collaborator map for buffer_post_from_folder from real app fns + stub the network ---
BP_COLLAB = {n: getattr(app_mod, n) for n in bp.REQUIRED_COLLABORATORS if hasattr(app_mod, n)}
# stub the Buffer network boundary + clickup + recovery side-effects
def fake_create_buffer_post(channel_id, text, media_paths, mode="addToQueue", metadata=None, scheduled_at=None):
    return {"id": f"buf_{channel_id}", "text": text, "channelId": channel_id, "captured_metadata": metadata}
BP_COLLAB["create_buffer_post"] = fake_create_buffer_post
BP_COLLAB["update_clickup_on_publish"] = lambda *a, **k: {"ok": True}
BP_COLLAB["record_recovery_event"] = lambda *a, **k: None
BP_COLLAB["advance_completed_chapter"] = lambda *a, **k: {"ok": True}
BP_COLLAB["github_auto_publish_media"] = lambda: False
# for routing tests we don't exercise the quality gate / video build
BP_COLLAB["folder_quality_gate"] = lambda *a, **k: {"ok": True}
BP_COLLAB["ensure_buffer_video"] = lambda *a, **k: None
BP_COLLAB["video_meets_minimum_duration"] = lambda *a, **k: True
# make the Buffer channel routing resolve. NOTE: load_env_file() (called inside
# release_state's ledger writes) re-reads .env.local and can clear BUFFER_CHANNEL_IDS,
# so re-assert it before each buffer_post_from_folder call.
CHANNEL_ENV = "instagram:ig1,tiktok:c1,youtube:yt1"
os.environ["BUFFER_CHANNEL_IDS"] = CHANNEL_ENV

# --- fixture TikTok folder -> buffer_post_from_folder returns {"posts":[...]} ---
tmp = Path(tempfile.mkdtemp(prefix="buf_test_"))
tk = tmp / "tk_pack"
tk.mkdir()
(tk / "metadata.json").write_text(json.dumps({
    "kind": "shorts", "abbr": "EN", "chapter": "10", "novel": "Eternal Nexus",
    "caption": "A short caption", "title": "Chapter 10",
}), encoding="utf-8")
(tk / "tiktok-video.mp4").write_text("fake", encoding="utf-8")
os.environ["BUFFER_CHANNEL_IDS"] = CHANNEL_ENV
res = bp.buffer_post_from_folder(str(tk), ["c1"], "tiktok", "addToQueue", collaborators=BP_COLLAB)
check("buffer_post_from_folder returns posts key", "posts" in res, True)
check("buffer_post_from_folder posts is list", isinstance(res["posts"], list), True)
# the routing produced a non-skipped post for the tiktok channel
nonskipped = [p for p in res["posts"] if isinstance(p, dict) and not p.get("skipped")]
check("buffer_post_from_folder produces a routed post", len(nonskipped) >= 1, True)


# --- Instagram image -> "post" type preserved in routing ---
# Routing branches are keyed on the folder's location under SOCIAL_OUTPUT_DIR, so the
# fixture must actually live there. Use a temp subfolder and clean it up after.
ig = Path(app_mod.SOCIAL_OUTPUT_DIR) / "ig_fixture_pack"
ig.mkdir(parents=True, exist_ok=True)
ig_meta = {
    "kind": "social_pack", "abbr": "EN", "chapter": "10", "novel": "Eternal Nexus",
    "instagram": "An instagram caption", "image": "img.png",
}
(ig / "metadata.json").write_text(json.dumps(ig_meta), encoding="utf-8")
(ig / "img.png").write_text("fake", encoding="utf-8")
os.environ["BUFFER_CHANNEL_IDS"] = CHANNEL_ENV
ig_res = bp.buffer_post_from_folder(str(ig), ["ig1"], "instagram", "addToQueue", collaborators=BP_COLLAB)
ig_posts = ig_res.get("posts", [])
ig_routed = [p for p in ig_posts if isinstance(p, dict) and not p.get("skipped")]
ig_metadata = ig_routed[0].get("captured_metadata") if ig_routed else None
check("instagram image pack routed to instagram service",
      any(isinstance(p, dict) and p.get("_automation", {}).get("service") == "instagram" for p in ig_posts), True)
check("instagram image pack post type preserved",
      ig_metadata, {"instagram": {"type": "post", "shouldShareToFeed": True}})
# cleanup fixture
import shutil
shutil.rmtree(ig, ignore_errors=True)

# --- Instagram reel (video) -> "reel" type preserved (TIKTOK folder branch) ---
reel = Path(app_mod.TIKTOK_OUTPUT_DIR) / "reel_fixture_pack"
reel.mkdir(parents=True, exist_ok=True)
reel_meta = {
    "kind": "shorts", "abbr": "EN", "chapter": "10", "novel": "Eternal Nexus",
    "instagram_reel_caption": "A reel caption", "caption": "A reel caption",
    "tiktok-video.mp4": "x",
}
(reel / "metadata.json").write_text(json.dumps(reel_meta), encoding="utf-8")
(reel / "tiktok-video.mp4").write_text("fake", encoding="utf-8")
os.environ["BUFFER_CHANNEL_IDS"] = CHANNEL_ENV
reel_res = bp.buffer_post_from_folder(str(reel), ["ig1"], "instagram", "addToQueue", collaborators=BP_COLLAB)
reel_routed = [p for p in reel_res.get("posts", []) if isinstance(p, dict) and not p.get("skipped")]
reel_metadata = reel_routed[0].get("captured_metadata") if reel_routed else None
check("instagram reel video pack post type preserved",
      reel_metadata, {"instagram": {"type": "reel", "shouldShareToFeed": True}})
shutil.rmtree(reel, ignore_errors=True)

# --- browser_publish: publish_x_post returns response (network stubbed) ---
BR_COLLAB = {n: getattr(app_mod, n) for n in br.REQUIRED_COLLABORATORS if hasattr(app_mod, n)}
def fake_multipart(url, token, fields, files):
    return {"data": {"id": "media123"}}
def fake_bearer(url, token, payload):
    return {"data": {"id": "tweet123"}}
BR_COLLAB["multipart_bearer_request"] = fake_multipart
BR_COLLAB["bearer_json_request"] = fake_bearer
BR_COLLAB["ensure_quality_gate"] = lambda *a, **k: {"ok": True}
BR_COLLAB["browser_launcher"] = lambda *a, **k: None
BR_COLLAB["open_url_once"] = lambda *a, **k: None
BR_COLLAB["clipboard_copy"] = lambda *a, **k: None

# fixture social folder for X
os.environ.setdefault("X_ACCESS_TOKEN", "test_token_for_parity")
xdir = Path(app_mod.SOCIAL_OUTPUT_DIR) / "x_fixture_pack"
xdir.mkdir(parents=True, exist_ok=True)
(xdir / "metadata.json").write_text(json.dumps({"x": "Hello X world", "image": str(xdir / "img.png")}), encoding="utf-8")
(xdir / "img.png").write_text("fake", encoding="utf-8")
xres = br.publish_x_post(str(xdir), collaborators=BR_COLLAB)
check("publish_x_post returns media_id", xres.get("media_id"), "media123")
check("publish_x_post returns post_response", xres.get("post_response", {}).get("data", {}).get("id"), "tweet123")
# structural parity with app.py (keys returned by the real fn, without live network)
check("publish_x_post returns expected keys", set(xres.keys()), {"media_id", "post_response"})

# --- manual_facebook_assist: injectable browser launcher, no real launch ---
launcher_calls = []
BR_COLLAB["browser_launcher"] = lambda folder: launcher_calls.append(folder)
fbres = br.manual_facebook_assist(str(xdir), collaborators=BR_COLLAB)
check("manual_facebook_assist returns folder", fbres.get("folder"), str(xdir.resolve()))
check("manual_facebook_assist invoked browser launcher", launcher_calls, [str(xdir.resolve())])

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS all buffer_publish + browser_publish characterization checks")
