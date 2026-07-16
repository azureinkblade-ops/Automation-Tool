"""Mutable process-local runtime state for the Automation Tool.

Holds objects that change at runtime: threading locks, background-thread
references, stop/pause events, and in-memory caches. NO immutable
configuration lives here (that is app_config.py). Subsystem modules
import this for their own locks/threads where practical; the app shell
imports it for the cross-cutting ones defined here.

Source of truth before extraction: app.py top-level locks/threads/caches
(lines ~203-310). Extracted per the consolidation plan; behavior unchanged.
"""
from __future__ import annotations

import threading
from pathlib import Path

# --- Threading locks (cross-cutting) ---
YOUTUBE_DAILY_LOCK = threading.Lock()
RELEASE_AUTOMATION_LOCK = threading.Lock()
DEEP_TIKTOK_ROTATION_LOCK = threading.Lock()
YOUTUBE_COMMENT_QUEUE_LOCK = threading.Lock()
METRICS_GATHER_LOCK = threading.Lock()
COMMENT_ASSISTANT_LOCK = threading.Lock()
CHATGPT_CHAPTER_LOCK = threading.Lock()
STORY_HOOK_LOCK = threading.Lock()
JSON_WRITE_LOCKS: dict[str, threading.RLock] = {}
JSON_WRITE_LOCKS_GUARD = threading.Lock()
MEDIA_PROBE_CACHE: dict[tuple[str, int, int], dict[str, object]] = {}

# --- Background thread references (None until spawned) ---
YOUTUBE_DAILY_THREAD: threading.Thread | None = None
RELEASE_AUTOMATION_THREAD: threading.Thread | None = None
AUTO_METRICS_THREAD: threading.Thread | None = None
COMMENT_ASSISTANT_THREAD: threading.Thread | None = None
CHATGPT_CHAPTER_THREAD: threading.Thread | None = None
STORY_HOOK_THREAD: threading.Thread | None = None

# --- Release-automation control events ---
RELEASE_AUTOMATION_STOP = threading.Event()
RELEASE_AUTOMATION_PAUSE = threading.Event()
