"""Test-owned guarded entrypoint; no parent launch authority is granted here."""

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    from tools.ea4e67y_worker_admission import validate_worker_launch
    from tools.ea4e67z_worker_containment import install_child_guard

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 5:
        raise ValueError("node, temporary root, and canonical worker argv required")
    node, base, *worker_argv = args
    validate_worker_launch(node, worker_argv, Path.cwd(), dict(os.environ), base, {})
    install_child_guard(base)
    # Load the frozen workload only after the child policy is installed.
    import runpy
    worker = runpy.run_path(worker_argv[1], run_name="guarded_local_worker")
    return worker["main"](worker_argv[2:])


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
