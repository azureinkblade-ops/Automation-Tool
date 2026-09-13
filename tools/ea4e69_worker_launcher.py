"""Test-owned bounded launch contract with an explicitly supplied factory."""

import hashlib
import subprocess

from tools import ea4e67y_worker_admission as admission
from tools.ea4e67z_worker_containment import OwnedChildren


SOURCE_HASHES = {
    "tools/ea4e68_worker_entrypoint.py": "eab863fb7e1c0aee921e46b34ea0493e71483bef7d514a58ff26f247064341a0",
    "tools/ea4e67y_worker_admission.py": "b37cea452fe52591f77c69cd2e8dcd13b580468f6a7babc34794cf7ddbce6ac8",
    "tools/ea4e67z_worker_containment.py": "540e6fb9b40b7a20bfabc01c7b9f0978d568648ba930f83e3f097b57bc553223",
}


def verify_bootstrap_sources():
    for relative, expected in SOURCE_HASHES.items():
        # Git's Windows checkout may change EOLs; pin canonical LF source.
        content = (admission.ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("bootstrap source mismatch: " + relative)


class BoundedWorkerLauncher:
    def __init__(self, factory):
        self.factory = factory
        self.admitted = {}
        self.owned = OwnedChildren()

    def spawn(self, node, argv, cwd, environment, basetemp):
        admission.validate_worker_launch(node, argv, cwd, environment, basetemp, self.admitted)
        verify_bootstrap_sources()
        command = [argv[0], "-B", str(admission.ROOT / "tools/ea4e68_worker_entrypoint.py"),
                   node, str(basetemp), *argv]
        # A failed or ambiguous creation still consumes its attempt budget.
        self.admitted[node] = self.admitted.get(node, 0) + 1
        child = self.factory(command, cwd=cwd, env=dict(environment), shell=False,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="replace")
        self.owned.register(child)
        return child

    def cleanup(self, timeout=1.0):
        self.owned.cleanup(timeout)
