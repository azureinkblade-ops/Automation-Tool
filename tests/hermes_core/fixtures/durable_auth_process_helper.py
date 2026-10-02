"""Exact subprocess entrypoint allowlisted for durable-store qualification."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tools.hermes_core.durable_invocation_authorization_store import (  # noqa: E402
    DurableInvocationAuthorizationStore,
)


def main(argv: list[str]) -> int:
    mode = argv[1]
    if mode == "precommit-crash":
        connection = sqlite3.connect(argv[2], isolation_level=None)
        connection.execute("BEGIN IMMEDIATE")
        os._exit(17)
    if mode == "claim":
        try:
            store = DurableInvocationAuthorizationStore(
                argv[2], anchor_path=argv[3]
            )
            payload = json.loads(argv[4])
            result = store.claim(
                payload,
                consumed_at=argv[5],
                validate=lambda: None,
            )
        except Exception:
            print("ERROR")
            return 1
        print("ALLOW" if result.allowed else "DENY")
        return 0
    raise ValueError(f"unsupported durable-store helper mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
