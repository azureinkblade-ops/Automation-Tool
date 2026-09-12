"""Use an explicitly synthetic report host; never run OS hostname probes."""

import platform

import pytest


REPORT_HOST = "NONLIVE_QUALIFICATION_NOT_OS_HOSTNAME"


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    original = platform.node
    platform.node = lambda: REPORT_HOST
    try:
        return (yield)
    finally:
        platform.node = original
