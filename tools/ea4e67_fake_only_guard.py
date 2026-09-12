"""Pytest tripwire for qualification runs, installed before test collection.

This is a Python-level tripwire, not an OS sandbox or universal capability deny.
"""

import os
import socket
import subprocess

import pytest


_originals = []
_events = []


def pytest_configure(config):
    def install(owner, name):
        original = getattr(owner, name)

        def denied(*args, **kwargs):
            _events.append(f"{owner.__name__}.{name}")
            raise RuntimeError(f"EA4E67 fake-only tripwire: {owner.__name__}.{name}")

        _originals.append((owner, name, original))
        setattr(owner, name, denied)

    for owner, name in ((subprocess, "Popen"), (os, "system"),
                        (socket.socket, "connect"), (socket.socket, "connect_ex")):
        install(owner, name)


def pytest_sessionfinish(session, exitstatus):
    if _events:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"EA4E67_FAKE_ONLY_TRIPWIRE_EVENTS={len(_events)}")
    for event in _events:
        terminalreporter.write_line(event)


def pytest_unconfigure(config):
    for owner, name, original in reversed(_originals):
        setattr(owner, name, original)
    _originals.clear()
