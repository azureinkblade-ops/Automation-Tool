"""Exact original pipe inputs for non-launching qualification admission."""

import hashlib
from pathlib import Path

from tools import ea4e67y_worker_admission as admission


PREFIX = "tests/hermes_core/test_opencode_adapter.py::"
CASES = {
    PREFIX + "TestOpenCodePipeCapture::test_stdout_capture": ("stdout", "import sys; sys.stdout.write('EA4E_PIPE_STDOUT_OK' + chr(10))"),
    PREFIX + "TestOpenCodePipeCapture::test_stderr_capture": ("stderr", "import sys; sys.stderr.write('EA4E_PIPE_STDERR_OK' + chr(10))"),
    PREFIX + "TestOpenCodePipeCapture::test_dual_stream_capture": ("dual", "import sys; sys.stdout.write('STDOUT_MARKER' + chr(10)); sys.stderr.write('STDERR_MARKER' + chr(10))"),
    PREFIX + "TestOpenCodePipeCapture::test_large_output_no_deadlock": ("large", "import sys; sys.stdout.write('X' * 200000)"),
    PREFIX + "TestOpenCodePipeCapture::test_zero_output_distinguishable": ("empty", "pass"),
    PREFIX + "TestOpenCodePipeCapture::test_timeout_lifecycle": ("timeout", "import time; time.sleep(30)"),
    PREFIX + "TestOpenCodePipeOverflow::test_stdout_over_1mb_limit": ("stdout_overflow", "import sys; sys.stdout.write('X' * (4 * 1024 * 1024))"),
    PREFIX + "TestOpenCodePipeOverflow::test_stderr_over_128kb_limit": ("stderr_overflow", "import sys; sys.stderr.write('Y' * (1024 * 1024))"),
    PREFIX + "TestOpenCodePipeOverflow::test_dual_stream_overflow": ("dual_overflow", "import sys; sys.stdout.write('A' * (2 * 1024 * 1024)); sys.stderr.write('B' * (512 * 1024))"),
    PREFIX + "TestOpenCodeReaderFinalization::test_stuck_reader_raises_capture_failure": ("reader_stuck", "import sys; sys.stdout.write('X' * 100)"),
    PREFIX + "TestOpenCodeReaderFinalization::test_reader_exception_raises_capture_failure": ("reader_error", "import sys; sys.stdout.write('X' * 100)"),
    PREFIX + "TestOpenCodeReaderFinalization::test_success_path_both_readers_dead": ("success", "import sys; sys.stdout.write('EA4E_SUCCESS' + chr(10))"),
    PREFIX + "TestOpenCodeRawCapture::test_no_synthetic_truncation_marker": ("raw", "import sys; sys.stdout.write('C' * (2 * 1024 * 1024))"),
    PREFIX + "TestOpenCodeMalformedOutput::test_malformed_jsonl_distinguishable": ("malformed", None),
    PREFIX + "TestOpenCodeCancellation::test_cancellation_preserves_ownership": ("cancel", "import time; time.sleep(60)"),
}
MALFORMED_SOURCE = "import sys\nsys.stdout.write('not json{{{invalid\\n')"


def pipe_case(node, command, cwd, basetemp):
    if node not in CASES or not isinstance(command, list) or not command:
        raise ValueError("unqualified pipe node/command")
    if Path(command[0]).resolve() != admission.PYTHON.resolve():
        raise ValueError("unqualified pipe interpreter")
    if hashlib.sha256(admission.PYTHON.read_bytes()).hexdigest() != admission.PYTHON_SHA256:
        raise ValueError("pipe interpreter identity mismatch")
    root = Path(cwd).resolve()
    base = Path(basetemp).resolve()
    if root == base or not root.is_dir() or not root.is_relative_to(base):
        raise ValueError("unqualified pipe child root")
    case, snippet = CASES[node]
    if snippet is not None:
        if command[1:] != ["-c", snippet]:
            raise ValueError("unqualified pipe snippet")
    else:
        script = root / "malformed.py"
        if command[1:] != [str(script)] or script.read_bytes().replace(b"\r\n", b"\n") != MALFORMED_SOURCE.encode("utf-8"):
            raise ValueError("unqualified malformed fixture")
    return case
