"""Image Pipeline V2 — persistent, profile-specific production activation control.

Authoritative owner of the V2 production activation flags. This replaces the
previous env-only / single-flag activation model with persistent, profile-specific
controls that survive restart and support deterministic rollback.

Controls:
  IMAGE_PIPELINE_V2_MAIN_POSTS_ENABLED   (default OFF)
  IMAGE_PIPELINE_V2_REALISTIC_ENABLED    (default OFF)

Design:
  - Persistent state lives in the feature worktree's STATE_ROOT (never the
    canonical automation_state.db).
  - Defaults are OFF / OFF; an unset state file behaves identically to OFF.
  - Main Posts and Realistic are independently controllable.
  - Comic is never authorized (always OFF; excluded from the supported set).
  - Tests can flip a profile via a thread-local override WITHOUT mutating the
    persistent file (see ``v2_activation_override``).
  - The router's own fail-closed firewall (comic/unknown -> fail closed) is
    preserved; this module only decides whether a *qualified* profile may route.

This module performs NO GPU work and NO ComfyUI I/O at import or read time.
"""

from __future__ import annotations

import contextlib
import json
import threading
from pathlib import Path
from typing import Dict, Iterator, Optional

import app_config as config

# --- Profile identity (canonical V2 profile ids) ----------------------------
MAIN_POSTS_PROFILE = "main_posts"
REALISTIC_PROFILE = "realistic"
COMIC_PROFILE = "comic"
# Canonical public name for the existing cinematic route. Activation storage
# stays on REALISTIC_PROFILE so the already-enabled cinematic flag remains
# equivalent. Photorealistic is not an activatable profile.
CINEMATIC_PROMO_PROFILE = "cinematic-promo"
PHOTOREALISTIC_PROFILE = "photorealistic"
PHOTOREALISTIC_PROFILE_AVAILABLE = False

SUPPORTED_PROFILES = (MAIN_POSTS_PROFILE, REALISTIC_PROFILE)
DEFAULT_STATE: Dict[str, bool] = {MAIN_POSTS_PROFILE: False, REALISTIC_PROFILE: False}

# Authoritative owner + storage (reported in evidence / final report).
ACTIVATION_CONTROL_OWNER = "tools/image_pipeline_v2_activation.py"
ACTIVATION_CONTROL_STORAGE = str(config.STATE_ROOT / "image_pipeline_v2_activation.json")
ACTIVATION_DEFAULT_MAIN_POSTS = False
ACTIVATION_DEFAULT_REALISTIC = False

_STATE_FILE = Path(ACTIVATION_CONTROL_STORAGE)
_lock = threading.RLock()


def get_state_file() -> Path:
    """Return the authoritative persistent state file path (STATE_ROOT-owned)."""
    return _STATE_FILE


@contextlib.contextmanager
def using_state_file(path) -> Iterator[Path]:
    """Temporarily repoint the persistent state file (isolated test fixtures).

    Does NOT touch the real production STATE_ROOT file. Restores the previous
    path on exit. Pair with `clear_v2_activation_overrides()` so thread-local
    overrides do not mask the persisted value under test.
    """
    global _STATE_FILE
    prior = _STATE_FILE
    _STATE_FILE = Path(path)
    try:
        yield _STATE_FILE
    finally:
        _STATE_FILE = prior

# Thread-local override so tests can force-enable a profile without touching the
# persistent state file. Keyed by profile -> bool.
_local = threading.local()


def _overrides() -> Dict[str, bool]:
    if not hasattr(_local, "overrides"):
        _local.overrides = {}
    return _local.overrides


def _read_persistent_state() -> Dict[str, bool]:
    """Return the persisted activation state merged over defaults.

    Missing file or malformed content degrades safely to all-OFF (fail closed).
    Never raises for storage issues; failures are treated as OFF.
    """
    state = dict(DEFAULT_STATE)
    try:
        if _STATE_FILE.exists():
            raw = _STATE_FILE.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for profile in SUPPORTED_PROFILES:
                    if profile in parsed and isinstance(parsed[profile], bool):
                        state[profile] = parsed[profile]
    except Exception:
        # Any storage failure -> default OFF (fail closed).
        return dict(DEFAULT_STATE)
    return state


def _write_persistent_state(state: Dict[str, bool]) -> None:
    """Atomically persist the activation state. Only supported profiles are written."""
    payload = {profile: bool(state.get(profile, False)) for profile in SUPPORTED_PROFILES}
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_FILE.with_name(f"{_STATE_FILE.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Best-effort atomic replace; fall back to plain write on locked filesystems.
    try:
        import os

        os.replace(tmp, _STATE_FILE)
    except OSError:
        _STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def is_v2_profile_enabled(profile: str, *, override: Optional[bool] = None) -> bool:
    """Return whether V2 routing is enabled for ``profile``.

    Resolution order (fail closed at every level):
      1. explicit ``override`` arg (used by tests / future prod callers),
      2. thread-local test override,
      3. persistent state file,
      4. default OFF.

    Comic, photorealistic, and any unknown profile always return False.
    cinematic-promo reads the existing realistic activation flag.
    """
    from tools.image_pipeline_v2_profiles import (
        PHOTOREALISTIC_PROFILE as _PHOTO,
        activation_storage_key,
    )

    if profile == _PHOTO:
        return False
    profile = activation_storage_key(profile)
    if profile not in SUPPORTED_PROFILES:
        return False
    if override is not None:
        return bool(override)
    ov = _overrides()
    if profile in ov:
        return bool(ov[profile])
    return bool(_read_persistent_state().get(profile, False))


def set_v2_profile_enabled(profile: str, enabled: bool) -> None:
    """Persistently enable/disable V2 routing for a supported profile.

    Raises ValueError for unsupported profiles (e.g. comic, photorealistic).
    cinematic-promo writes the existing realistic flag; it is not a second switch.
    """
    from tools.image_pipeline_v2_profiles import (
        PHOTOREALISTIC_PROFILE as _PHOTO,
        activation_storage_key,
    )

    if profile == _PHOTO:
        raise ValueError(
            "V2 activation for 'photorealistic' is not supported "
            "(PHOTOREALISTIC_PROFILE_AVAILABLE=NO; unqualified profile is fail-closed)"
        )
    profile = activation_storage_key(profile)
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(
            f"V2 activation for {profile!r} is not supported "
            f"(supported={SUPPORTED_PROFILES}; comic is NOT_AUTHORIZED; "
            "photorealistic is UNAVAILABLE)"
        )
    with _lock:
        state = _read_persistent_state()
        state[profile] = bool(enabled)
        _write_persistent_state(state)


def reset_v2_activation_state() -> None:
    """Reset persistent activation state to defaults (OFF/OFF)."""
    with _lock:
        _write_persistent_state(dict(DEFAULT_STATE))


def load_v2_activation_state() -> Dict[str, bool]:
    """Return a snapshot of the persistent activation state."""
    return dict(_read_persistent_state())


def clear_v2_activation_overrides() -> None:
    """Clear any thread-local test overrides."""
    _overrides().clear()


class v2_activation_override:
    """Context manager to force a profile's activation state for a test scope.

    Does NOT mutate the persistent state file; restores the previous override
    (or absence) on exit.
    """

    def __init__(self, profile: str, enabled: bool):
        self.profile = profile
        self.enabled = bool(enabled)
        self._prior: Optional[bool] = None
        self._had_prior = False

    def __enter__(self) -> "v2_activation_override":
        ov = _overrides()
        self._had_prior = self.profile in ov
        if self._had_prior:
            self._prior = ov[self.profile]
        ov[self.profile] = self.enabled
        return self

    def __exit__(self, *exc: object) -> None:
        ov = _overrides()
        if self._had_prior:
            ov[self.profile] = self._prior  # type: ignore[assignment]
        else:
            ov.pop(self.profile, None)
