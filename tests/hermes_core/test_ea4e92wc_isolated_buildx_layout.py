"""Synthetic, no-Docker checks for the isolated Buildx search layout."""

import hashlib

import pytest

from tools import ea4e92wc_isolated_buildx_layout as policy
from tools.ea4e92wc_isolated_buildx_layout import (
    LayoutDenied, isolated_environment,
)


def layout(tmp_path):
    config = tmp_path / "config"
    program = tmp_path / "program"
    plugin_dir = program / "Docker" / "cli-plugins"
    config.mkdir()
    plugin_dir.mkdir(parents=True)
    plugin = plugin_dir / "docker-buildx.exe"
    plugin.write_bytes(b"synthetic buildx")
    return config, program, plugin


def pin(plugin):
    return hashlib.sha256(plugin.read_bytes()).hexdigest()


def test_exact_single_plugin_environment(tmp_path):
    config, program, plugin = layout(tmp_path)
    environment = isolated_environment(config, program, pin(plugin))
    assert environment["DOCKER_CONFIG"] == str(config)
    assert environment["ProgramFiles"] == str(program)
    assert set(environment) == {"SYSTEMROOT", "DOCKER_CONFIG", "ProgramFiles"}


def test_extra_plugin_denied(tmp_path):
    config, program, plugin = layout(tmp_path)
    (plugin.parent / "docker-compose.exe").write_bytes(b"synthetic")
    with pytest.raises(LayoutDenied, match="layout mismatch"):
        isolated_environment(config, program, pin(plugin))


def test_nonempty_config_denied(tmp_path):
    config, program, plugin = layout(tmp_path)
    (config / "config.json").write_text("{}", encoding="ascii")
    with pytest.raises(LayoutDenied, match="layout mismatch"):
        isolated_environment(config, program, pin(plugin))


def test_plugin_drift_denied(tmp_path):
    config, program, plugin = layout(tmp_path)
    with pytest.raises(LayoutDenied, match="layout mismatch"):
        isolated_environment(config, program, "a" * 64)


def test_inventory_error_has_no_raw_context(monkeypatch, tmp_path):
    config, program, plugin = layout(tmp_path)
    original = type(config).iterdir

    def fail_config(path):
        if path == config:
            raise OSError(r"private path C:\secret\config")
        return original(path)

    monkeypatch.setattr(type(config), "iterdir", fail_config)
    with pytest.raises(LayoutDenied, match="layout unavailable") as error:
        isolated_environment(config, program, pin(plugin))
    assert error.value.__context__ is None
    assert error.value.__cause__ is None


def test_plugin_read_error_has_no_raw_context(monkeypatch, tmp_path):
    config, program, plugin = layout(tmp_path)
    expected = pin(plugin)
    original = type(plugin).open

    def fail_plugin(path, *args, **kwargs):
        if path == plugin:
            raise OSError(r"private path C:\secret\docker-buildx.exe")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(type(plugin), "open", fail_plugin)
    with pytest.raises(LayoutDenied, match="plugin unavailable") as error:
        isolated_environment(config, program, expected)
    assert error.value.__context__ is None
    assert error.value.__cause__ is None


def test_reparse_plugin_denied(monkeypatch, tmp_path):
    config, program, plugin = layout(tmp_path)
    expected = pin(plugin)
    plain = policy._plain
    monkeypatch.setattr(policy, "_plain",
                        lambda path, *, directory: False if path == plugin
                        else plain(path, directory=directory))
    with pytest.raises(LayoutDenied, match="layout mismatch"):
        isolated_environment(config, program, expected)


def test_reparse_ancestor_denied(monkeypatch, tmp_path):
    config, program, plugin = layout(tmp_path)
    expected = pin(plugin)
    plain = policy._plain
    ancestor = tmp_path.parent
    monkeypatch.setattr(policy, "_plain",
                        lambda path, *, directory: False if path == ancestor
                        else plain(path, directory=directory))
    with pytest.raises(LayoutDenied, match="layout mismatch"):
        isolated_environment(config, program, expected)


def test_parent_alias_denied(tmp_path):
    config, program, plugin = layout(tmp_path)
    alias = config / ".." / "config"
    with pytest.raises(LayoutDenied, match="layout mismatch"):
        isolated_environment(alias, program, pin(plugin))
