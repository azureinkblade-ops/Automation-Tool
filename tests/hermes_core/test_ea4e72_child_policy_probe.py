"""One owned deterministic child, without actual network or nested launch."""

import json
import os
import subprocess

from tools import ea4e67y_worker_admission as admission
from tools.ea4e67z_worker_containment import OwnedChildren


def test_installed_child_policy_denies_escape(tmp_path):
    root = tmp_path / "child"
    root.mkdir()
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "SYSTEMDRIVE") if name in os.environ}
    environment.update(TEMP=str(root), TMP=str(root))
    owned = OwnedChildren()
    child = subprocess.Popen([str(admission.PYTHON), "-B", str(admission.ROOT / "tools/ea4e72_child_policy_probe.py"), str(root)],
                             cwd=admission.ROOT, env=environment, shell=False,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="replace")
    owned.register(child)
    try:
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 0, stderr
        assert json.loads(stdout) == {"socket_event": True, "process_event": True, "shell_event": True,
                                     "file_escape": True, "sqlite_escape": True,
                                     "inside_file": True, "inside_sqlite": True}
        assert not (tmp_path / "escaped.txt").exists()
        assert not (tmp_path / "escaped.sqlite3").exists()
        assert (root / "allowed.txt").is_file()
        assert (root / "allowed.sqlite3").is_file()
    finally:
        owned.cleanup()
    assert child.poll() is not None
    assert all(pipe.closed for pipe in (child.stdin, child.stdout, child.stderr))
