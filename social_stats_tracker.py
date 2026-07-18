"""
Daily social-stats tracker for the author channels.

Runs ONCE PER DAY when the app opens (guarded by a last_run timestamp in the
state DB). Collects stats for all author channels at once:
  - Buffer-managed channels: Facebook, Instagram, TikTok  (via buffer_publish GraphQL)
  - YouTube (via YouTube Data API; YouTube Analytics API if an OAuth token exists)

Output: one row per (platform, channel, date) in automation_db.social_stats_daily,
so the app UI can render cross-channel trends. Per-post detail falls back to
platform_post_metrics where the upstream API exposes it.

Fail-soft: any channel/API that is unavailable (missing tier, expired token,
rate limit) is logged and skipped; the run still records what it could.

Secrets: read from .env.local at runtime only. Never echo tokens.
"""
from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
import json
from datetime import date

from pathlib import Path

import automation_db

ROOT = Path(os.environ.get("APP_ROOT", r"C:\Users\David\Documents\Automation tool"))
LAST_RUN_KEY = "social_stats_last_run"
RUN_INTERVAL_SECONDS = 24 * 60 * 60  # once per day


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _env() -> dict[str, str]:
    d: dict[str, str] = {}
    path = ROOT / ".env.local"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _http_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Buffer channels (Facebook, Instagram, TikTok)
# --------------------------------------------------------------------------
def _buffer_org_id() -> str | None:
    """Buffer GraphQL requires organizationId on read queries. Fetch from account."""
    try:
        import buffer_publish
        data = buffer_publish.buffer_graphql('query { account { organizations { id name } } }')
        orgs = (data.get("data") or {}).get("account", {}).get("organizations") or []
        return orgs[0].get("id") if orgs else None
    except Exception:
        return None


def collect_buffer_stats(env: dict[str, str]) -> list[dict]:
    """Pull per-channel stats for Buffer-managed profiles (Facebook, Instagram, TikTok).

    Uses buffer_publish.buffer_graphql (the same authenticated client the app uses
    to post). Reads SENT posts per channel via the `posts(input: {organizationId,
    filter:{channelIds, status:sent}})` connection and aggregates the per-post
    `metrics` list (name/value) into totals. REQUIRES the `insights:read` OAuth
    scope on the Buffer app; without it Buffer returns "Insufficient scope".
    Fail-soft per channel.
    """
    out: list[dict] = []
    try:
        import buffer_publish
    except Exception as exc:
        print(f"[social-stats] buffer_publish import failed: {exc}")
        return out

    try:
        channels = buffer_publish.configured_buffer_channels()
    except Exception as exc:
        print(f"[social-stats] could not list buffer channels: {exc}")
        return out

    if not channels:
        out.append({"platform": "buffer", "channel": "none",
                    "metrics": {"available": False, "note": "BUFFER_CHANNEL_IDS empty"}})
        return out

    org = _buffer_org_id()
    if not org:
        out.append({"platform": "buffer", "channel": "none",
                    "metrics": {"available": False, "note": "could not resolve Buffer organizationId"}})
        return out

    for ch in channels:
        channel_id = ch.get("id") or ch.get("channel_id") or ""
        service = (ch.get("service") or ch.get("type") or "buffer").lower()
        name = ch.get("name") or ch.get("display_name") or channel_id
        metrics: dict[str, object] = {"source": "buffer", "available": False}
        try:
            query = (
                'query { posts(input: {organizationId: "' + org + '", '
                'filter: {channelIds: ["' + channel_id + '"], status: sent}}, first: 50) { '
                'edges { node { id channelService metrics { name value } } } } }'
            )
            data = buffer_publish.buffer_graphql(query)
            edges = ((data.get("data") or {}).get("posts") or {}).get("edges") or []
            agg: dict[str, float] = {}
            for e in edges:
                for m in ((e.get("node") or {}).get("metrics") or []):
                    agg[m["name"]] = agg.get(m["name"], 0) + float(m.get("value") or 0)
            metrics["available"] = True
            metrics["posts_sent"] = len(edges)
            for k, v in agg.items():
                metrics[k] = int(v)
        except Exception as exc:
            err = str(exc)
            if "Insufficient scope" in err or "insights:read" in err:
                metrics["error"] = "Buffer token missing 'insights:read' scope — add it to the Buffer app OAuth and re-auth"
                metrics["blocker"] = "insights:read"
            else:
                metrics["error"] = f"{type(exc).__name__}: {err[:160]}"
        out.append({"platform": service, "channel": name, "metrics": metrics})
    return out


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------
def collect_youtube_stats(env: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    key = env.get("YOUTUBE_DATA_API_KEY")
    channel_id = env.get("YOUTUBE_CHANNEL_ID")
    if not key or not channel_id:
        out.append({"platform": "youtube", "channel": channel_id or "youtube",
                    "metrics": {"available": False, "note": "missing YOUTUBE keys"}})
        return out

    metrics: dict[str, object] = {"source": "youtube", "available": True}
    # Data API: channel statistics (subs, views, videos)
    try:
        url = ("https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet"
               f"&id={urllib.parse.quote(channel_id)}&key={urllib.parse.quote(key)}")
        data = _http_json(url)
        items = data.get("items") or []
        if items:
            stats = items[0].get("statistics", {})
            metrics["subscribers"] = int(stats.get("subscriberCount", 0) or 0)
            metrics["total_views"] = int(stats.get("viewCount", 0) or 0)
            metrics["video_count"] = int(stats.get("videoCount", 0) or 0)
            snippet = items[0].get("snippet", {})
            metrics["title"] = snippet.get("title", "")
    except Exception as exc:
        metrics["available"] = False
        metrics["error"] = f"{type(exc).__name__}: {exc}"

    # Optional: YouTube Analytics API (OAuth) for daily reach/engagement.
    token = env.get("YOUTUBE_ANALYTICS_TOKEN")
    if token:
        try:
            today = date.today().isoformat()
            ana_url = (
                "https://youtubeanalytics.googleapis.com/v2/reports"
                f"?ids=channel=={urllib.parse.quote(channel_id)}"
                f"&startDate={today}&endDate={today}"
                "&metrics=views,likes,comments,shares,estimatedMinutesWatched"
                "&dimensions=day&access_token=" + urllib.parse.quote(token)
            )
            ana = _http_json(ana_url)
            rows = ana.get("rows") or []
            if rows and rows[0]:
                cols = [c["name"] for c in ana.get("columnHeaders", [])]
                for col, val in zip(cols, rows[0]):
                    metrics[f"daily_{col}"] = val
        except Exception as exc:
            metrics["analytics_error"] = f"{type(exc).__name__}: {exc}"
    else:
        metrics["analytics_note"] = "no YOUTUBE_ANALYTICS_TOKEN; Data API stats only"

    out.append({"platform": "youtube", "channel": channel_id, "metrics": metrics})
    return out


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------
def run_daily_social_stats() -> dict:
    env = _env()
    collected_date = date.today().isoformat()
    results: list[dict] = []
    results += collect_buffer_stats(env)
    results += collect_youtube_stats(env)

    for r in results:
        try:
            automation_db.save_social_stats_daily(
                ROOT, r["platform"], r["channel"], collected_date, r["metrics"]
            )
        except Exception as exc:
            print(f"[social-stats] db write failed for {r['platform']}/{r['channel']}: {exc}")

    automation_db.upsert_state_snapshot(
        ROOT, LAST_RUN_KEY, {"last_run": time.strftime("%Y-%m-%d %H:%M:%S"), "channels": len(results)}
    )
    print(f"[social-stats] collected {len(results)} channels for {collected_date}")
    return {"date": collected_date, "channels": results}


def should_run() -> bool:
    snap = automation_db.load_state_snapshot(ROOT, LAST_RUN_KEY)
    if not snap:
        return True
    last = snap.get("last_run")
    if not last:
        return True
    try:
        last_ts = time.mktime(time.strptime(last, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return True
    return (time.time() - last_ts) >= RUN_INTERVAL_SECONDS


def daily_social_stats_worker() -> None:
    """Called from app startup. Runs at most once per day."""
    try:
        if not should_run():
            print("[social-stats] already ran within 24h; skipping.")
            return
        run_daily_social_stats()
    except Exception as exc:
        print(f"[social-stats] worker error: {exc}")


if __name__ == "__main__":
    daily_social_stats_worker()
