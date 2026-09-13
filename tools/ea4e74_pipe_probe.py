"""Enumerated deterministic pipe workload; never evaluates task text."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def main(case, root):
    from tools.ea4e67z_worker_containment import install_child_guard
    install_child_guard(root)
    import time

    if case == "stdout":
        sys.stdout.write("EA4E_PIPE_STDOUT_OK\n")
    elif case == "stderr":
        sys.stderr.write("EA4E_PIPE_STDERR_OK\n")
    elif case == "dual":
        sys.stdout.write("STDOUT_MARKER\n")
        sys.stderr.write("STDERR_MARKER\n")
    elif case == "large":
        sys.stdout.write("X" * 200000)
    elif case == "empty":
        pass
    elif case == "timeout":
        time.sleep(30)
    elif case == "stdout_overflow":
        sys.stdout.write("X" * (4 * 1024 * 1024))
    elif case == "stderr_overflow":
        sys.stderr.write("Y" * (1024 * 1024))
    elif case == "dual_overflow":
        sys.stdout.write("A" * (2 * 1024 * 1024))
        sys.stderr.write("B" * (512 * 1024))
    elif case in {"reader_stuck", "reader_error"}:
        sys.stdout.write("X" * 100)
    elif case == "success":
        sys.stdout.write("EA4E_SUCCESS\n")
    elif case == "raw":
        sys.stdout.write("C" * (2 * 1024 * 1024))
    elif case == "malformed":
        sys.stdout.write("not json{{{invalid\n")
    elif case == "cancel":
        time.sleep(60)
    else:
        raise ValueError("unqualified pipe case")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    if len(sys.argv) != 3:
        raise ValueError("exact pipe case and child root required")
    sys.exit(main(sys.argv[1], Path(sys.argv[2]).resolve()))
