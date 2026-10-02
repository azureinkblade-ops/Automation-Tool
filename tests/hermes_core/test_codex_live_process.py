from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.hermes_core.codex_adapter import CodexArgv, CodexProcessError
from tools.hermes_core.codex_live_process import CodexLiveProcess


class _Pipe:
    def __init__(self, error=None):
        self.data = b""
        self.closed = False
        self.error = error
    def write(self, data):
        if self.error:
            raise self.error
        self.data += data
    def close(self):
        self.closed = True


class _Process:
    def __init__(self, args, *, pid=4321, returncode=None, **kwargs):
        self.args = args
        self.pid = pid
        self.returncode = returncode
        self.stdin = _Pipe()
        self.terminated = False
        self.killed = False
        self.kwargs = kwargs
    def poll(self):
        return self.returncode
    def terminate(self):
        self.terminated = True
        self.returncode = 1
    def kill(self):
        self.killed = True
        self.returncode = 1


class CodexLiveProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.output = root / "spool" / "run.json"
        self.argv = CodexArgv(
            executable="C:/trusted/codex.exe",
            args=("exec", "--output-last-message", str(self.output), "-"),
            cwd=str(root), env=(("CODEX_HOME", str(root / "codex-home")),),
            input_schema_file=str(root / "schema.json"),
            output_file=str(self.output), shell=False,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_structured_spawn_and_bounded_collection(self):
        captured = {}
        def factory(args, **kwargs):
            captured.update(kwargs)
            process = _Process(args, returncode=None, **kwargs)
            captured["process"] = process
            return process
        controller = CodexLiveProcess(popen=factory, monotonic=lambda: 10.0)
        pid = controller.start(self.argv, '{"task":"bounded"}')
        process = captured["process"]
        self.assertEqual(process.stdin.data, b'{"task":"bounded"}')
        self.assertTrue(process.stdin.closed)
        self.assertFalse(captured["shell"])
        self.assertEqual(controller.poll(pid), None)
        self.output.write_text('{"schema_version":"1"}', encoding="utf-8")
        Path(captured["stdout"].name).write_text('{"type":"thread.started"}\n', encoding="utf-8")
        Path(captured["stderr"].name).write_text("diagnostic", encoding="utf-8")
        process.returncode = 0
        result = controller.poll(pid)
        self.assertEqual(result.pid, pid)
        self.assertEqual(result.returncode, 0)
        self.assertIn("thread.started", result.stdout)
        self.assertEqual(result.stderr, "diagnostic")
        self.assertEqual(result.final_output, '{"schema_version":"1"}')

    def test_refuses_preexisting_output_and_foreign_pid(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text("existing", encoding="utf-8")
        with self.assertRaises(CodexProcessError):
            CodexLiveProcess(popen=lambda *a, **k: _Process(a[0])).start(self.argv, "{}")
        with self.assertRaises(CodexProcessError):
            CodexLiveProcess().poll(999)

    def test_terminate_and_kill_only_owned_process(self):
        holder = {}
        def factory(args, **kwargs):
            holder["process"] = _Process(args, **kwargs)
            return holder["process"]
        controller = CodexLiveProcess(popen=factory)
        pid = controller.start(self.argv, "{}")
        controller.terminate(pid)
        self.assertTrue(holder["process"].terminated)
        with self.assertRaises(CodexProcessError):
            controller.kill(999)

    def test_stdin_failure_after_spawn_preserves_definitive_start(self):
        holder = {}
        def factory(args, **kwargs):
            process = _Process(args, **kwargs)
            process.stdin = _Pipe(BrokenPipeError("child exited"))
            holder["process"] = process
            return process
        controller = CodexLiveProcess(popen=factory)
        pid = controller.start(self.argv, "{}")
        self.assertEqual(pid, holder["process"].pid)
        self.assertTrue(holder["process"].terminated)
        self.assertEqual(controller.poll(pid).returncode, 1)


if __name__ == "__main__":
    unittest.main()
