"""Synthetic tests for the opt-in isolated Buildx inspect transport."""

import hashlib
import io
from pathlib import Path

import pytest

from tools import ea4e92rm_container_smoke as smoke
from tools.ea4e92wc_isolated_buildx_layout import IsolatedBuildxLayout


class SuccessProcess:
    stdin = io.BytesIO()
    stderr = io.BytesIO()
    returncode = 0

    def __init__(self, stdout):
        self.stdout = io.BytesIO(stdout)

    def wait(self, timeout):
        return self.returncode

    def poll(self):
        return self.returncode


def fixture_layout(tmp_path):
    config = tmp_path / "config"
    program = tmp_path / "program"
    plugin_dir = program / "Docker" / "cli-plugins"
    config.mkdir()
    plugin_dir.mkdir(parents=True)
    plugin = plugin_dir / "docker-buildx.exe"
    plugin.write_bytes(b"synthetic plugin")
    digest = hashlib.sha256(plugin.read_bytes()).hexdigest()
    return IsolatedBuildxLayout(config, program, digest), plugin


def client(monkeypatch, layout):
    monkeypatch.setattr(smoke, "_hash_file", lambda path: "a" * 64)
    return smoke.DockerCli(Path(__file__), "a" * 64,
                           classify_buildx_inspect_failure=True,
                           isolated_buildx_layout=layout)


def test_exact_isolated_call_returns_only_fixed_result(monkeypatch, tmp_path):
    layout, _ = fixture_layout(tmp_path)
    seen = []
    result = (b"Name: default\nDriver: docker\n"
              b"Endpoint: npipe:////./pipe/dockerDesktopLinuxEngine\n")
    monkeypatch.setattr(smoke.subprocess, "Popen",
                        lambda *a, **k: (seen.append((a, k)),
                                         SuccessProcess(result))[1])
    transport = client(monkeypatch, layout)
    assert transport.invoke(("buildx", "inspect", "default"),
                            timeout=1, output_limit=65536) == b"local_default_docker"
    assert seen[0][0][0][-3:] == ("buildx", "inspect", "default")
    assert seen[0][1]["env"] == {
        "SYSTEMROOT": smoke.os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "DOCKER_CONFIG": str(layout.config_dir),
        "ProgramFiles": str(layout.program_files),
    }
    assert seen[0][1]["cwd"] == str(layout.config_dir)


def test_other_command_denied_before_start(monkeypatch, tmp_path):
    layout, _ = fixture_layout(tmp_path)
    monkeypatch.setattr(smoke.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("Docker started"))
    transport = client(monkeypatch, layout)
    with pytest.raises(smoke.SmokeDenied, match="isolated builder command denied"):
        transport.invoke(("container", "ls"), timeout=1)


def test_layout_drift_denied_before_start(monkeypatch, tmp_path):
    layout, plugin = fixture_layout(tmp_path)
    transport = client(monkeypatch, layout)
    (plugin.parent / "docker-compose.exe").write_bytes(b"synthetic")
    monkeypatch.setattr(smoke.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("Docker started"))
    with pytest.raises(smoke.SmokeDenied, match="isolated builder layout denied"):
        transport.invoke(("buildx", "inspect", "default"), timeout=1)


def test_nonlocal_endpoint_denied_without_raw_output(monkeypatch, tmp_path):
    layout, _ = fixture_layout(tmp_path)
    result = (b"Name: default\nDriver: docker\n"
              b"Endpoint: tcp://private.example:2375\n")
    monkeypatch.setattr(smoke.subprocess, "Popen",
                        lambda *a, **k: SuccessProcess(result))
    transport = client(monkeypatch, layout)
    with pytest.raises(smoke.SmokeDenied, match="isolated builder result denied") as error:
        transport.invoke(("buildx", "inspect", "default"), timeout=1)
    assert "private.example" not in str(error.value)


def test_layout_drift_after_call_denied(monkeypatch, tmp_path):
    layout, plugin = fixture_layout(tmp_path)
    transport = client(monkeypatch, layout)
    result = (b"Name: default\nDriver: docker\n"
              b"Endpoint: npipe:////./pipe/dockerDesktopLinuxEngine\n")

    def drift(*args, **kwargs):
        (plugin.parent / "docker-compose.exe").write_bytes(b"synthetic")
        return SuccessProcess(result)

    monkeypatch.setattr(smoke.subprocess, "Popen", drift)
    with pytest.raises(smoke.SmokeDenied, match="isolated builder layout drift"):
        transport.invoke(("buildx", "inspect", "default"), timeout=1)


def test_duplicate_endpoint_denied(monkeypatch, tmp_path):
    layout, _ = fixture_layout(tmp_path)
    result = (b"Name: default\nDriver: docker\n"
              b"Endpoint: npipe:////./pipe/dockerDesktopLinuxEngine\n"
              b"Endpoint: tcp://private.example:2375\n")
    monkeypatch.setattr(smoke.subprocess, "Popen",
                        lambda *a, **k: SuccessProcess(result))
    transport = client(monkeypatch, layout)
    with pytest.raises(smoke.SmokeDenied, match="isolated builder result denied"):
        transport.invoke(("buildx", "inspect", "default"), timeout=1)
