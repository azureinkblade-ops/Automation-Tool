"""Retain qualification evidence without expanding frozen process admission."""

from pathlib import Path
import shutil

from tools import ea4e67j_durability_process_guard as frozen


_original = None
_retained = []


def retain_tree(path, roots):
    target = Path(path).resolve()
    if not any(target == root or target.is_relative_to(root) for root in roots):
        raise RuntimeError(f"durability cleanup outside isolated roots denied: {target}")
    _retained.append(str(target))


def pytest_configure(config):
    global _original
    frozen.pytest_configure(config)
    base = Path(config.option.basetemp).resolve()
    roots = (base, base.with_name(base.name + "-helpers"))
    _original = shutil.rmtree

    def retained(path, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            raise RuntimeError("descriptor-relative cleanup denied")
        retain_tree(path, roots)

    shutil.rmtree = retained


def pytest_sessionfinish(session, exitstatus):
    frozen.pytest_sessionfinish(session, exitstatus)


def pytest_sessionstart(session):
    # The frozen guard created this fresh root; pytest must not remove it.
    session.config._tmp_path_factory._basetemp = Path(
        session.config.option.basetemp
    ).resolve()


def pytest_terminal_summary(terminalreporter):
    frozen.pytest_terminal_summary(terminalreporter)
    terminalreporter.write_line(f"EA4E90_RETAINED_TREES={len(_retained)}")


def pytest_unconfigure(config):
    global _original
    if _original is not None:
        shutil.rmtree = _original
        _original = None
    frozen.pytest_unconfigure(config)
