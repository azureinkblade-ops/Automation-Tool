"""Kilo agent profile for Hermes EA-4E.3 governed receiver.

The Hermes-owned Kilo agent profile is created under the Hermes-controlled
runtime root (not inside the repo), so ambient Kilo/OpenCode config cannot
weaken the deny-all permission policy.

This module creates the profile on first import (if missing) and provides
the AGENT_DEFINITION string consumed by the tests and the transport builder.

Rules:
- No live Kilo model task.
- No prompt submission.
- No live ACP work session.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.hermes_core.kilo_adapter import (
    KILO_EFFECTIVE_HOME,
    KILO_CONFIG_DIR,
)


AGENT_ID = "hermes-ea4e-kilo-receiver"
AGENT_FILENAME = f"{AGENT_ID}.jsonc"
AGENT_DIR = KILO_EFFECTIVE_HOME / ".kilo" / "agents" / AGENT_ID
AGENT_FILE = AGENT_DIR / AGENT_FILENAME
AGENT_HASHCACHE = KILO_CONFIG_DIR / "agent_hash.txt"

AGENT_DEFINITION = """\
{
  "name": "hermes-ea4e-kilo-receiver",
  "description": "Hermes EA-4E.3 governed Kilo receiver agent. Non-live qualification only.",
  "version": "1.0.0",
  "profile_owner": "HERMES",
  "qualification": "EA-4E.3 non-live",
  "live_authorized": false,
  "model_selection": "DEFERRED to live-mechanical-governance gate",
  "config_isolation": "HOME, OPENCODE_CONFIG_DIR, KILO_CONFIG_DIR redirected to Hermes-controlled runtime root",
  "permission": {
    "*": "deny",
    "read": {"*": "deny"},
    "edit": "deny",
    "write": "deny",
    "bash": "deny",
    "glob": {"*": "deny"},
    "grep": {"*": "deny"},
    "list": "deny",
    "mcp": "deny",
    "plugin": "deny",
    "agent": "deny",
    "browser": "deny",
    "web": "deny",
    "fetch": "deny"
  },
  "agents": {},
  "plugins": {},
  "mcpServers": {}
}
"""


def ensure_agent_profile() -> Path:
    """Create the Hermes Kilo agent profile directory and file if missing."""
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    if not AGENT_FILE.exists():
        AGENT_FILE.write_text(AGENT_DEFINITION, encoding="utf-8")
    return AGENT_DIR


def agent_profile_hash() -> str:
    """Return the SHA-256 of the agent profile JSONC content."""
    ensure_agent_profile()
    content = AGENT_FILE.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "AGENT_ID",
    "AGENT_DIR",
    "AGENT_FILE",
    "AGENT_DEFINITION",
    "ensure_agent_profile",
    "agent_profile_hash",
    "AGENT_HASHCACHE",
]
