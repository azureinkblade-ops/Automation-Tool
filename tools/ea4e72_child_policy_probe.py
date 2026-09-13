"""Deterministic child policy proof; no network calls or nested processes."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    from tools.ea4e67z_worker_containment import install_child_guard
    if len(sys.argv) != 2:
        raise ValueError("one isolated child root required")
    root = Path(sys.argv[1]).resolve()
    install_child_guard(root)
    import json
    import sqlite3

    def denied(operation):
        try:
            operation()
        except RuntimeError:
            return True
        return False

    def database(path):
        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE proof (value INTEGER)")
            conn.commit()
        finally:
            conn.close()

    results = {
        "socket_event": denied(lambda: sys.audit("socket.connect", None, ("127.0.0.1", 9))),
        "process_event": denied(lambda: sys.audit("subprocess.Popen", "not-executed", [], None, {})),
        "shell_event": denied(lambda: sys.audit("os.system", b"not-executed")),
        "file_escape": denied(lambda: (root.parent / "escaped.txt").write_text("escape", encoding="utf-8")),
        "sqlite_escape": denied(lambda: database(root.parent / "escaped.sqlite3")),
    }
    (root / "allowed.txt").write_text("allowed", encoding="utf-8")
    database(root / "allowed.sqlite3")
    results["inside_file"] = (root / "allowed.txt").read_text(encoding="utf-8") == "allowed"
    results["inside_sqlite"] = True
    print(json.dumps(results, sort_keys=True))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
