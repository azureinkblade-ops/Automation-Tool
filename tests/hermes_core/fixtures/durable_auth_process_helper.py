"""Exact subprocess entrypoint allowlisted for durable-store qualification."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

def deny_runtime_capabilities(event, args):
    if event.startswith(("subprocess.", "socket.")) or event in {
        "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
    }:
        raise RuntimeError(f"durability helper prohibited capability: {event}")


sys.addaudithook(deny_runtime_capabilities)

from tools.hermes_core.durable_invocation_authorization_store import (  # noqa: E402
    DurableInvocationAuthorizationStore,
)


def main(argv: list[str]) -> int:
    mode = argv[1]
    if mode == "precommit-crash":
        connection = sqlite3.connect(argv[2], isolation_level=None)
        connection.execute("BEGIN IMMEDIATE")
        os._exit(17)
    if mode in {"claim", "postcommit-crash"}:
        try:
            store = DurableInvocationAuthorizationStore(
                argv[2], anchor_path=argv[3]
            )
            payload = json.loads(argv[4])
            if mode == "postcommit-crash":
                store._after_database_commit_before_anchor = lambda: os._exit(23)
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
