# -*- coding: utf-8 -*-
"""Repo-root conftest: PYTEST_LIVE_SIDE_EFFECT_ISOLATION.

The live side-effect barrier (network deny, subprocess barrier, credential strip,
output redirect) is installed at IMPORT time of this file - before tests/conftest.py
and before any test module is imported or collected.  tests/conftest.py also
installs it first thing, for runs whose rootdir resolves to tests/.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from tests import live_side_effect_barrier as _lsb  # noqa: E402

_lsb.install()

pytest_plugins = ["tests.live_side_effect_hooks"]

# Collection hardening: tests/test_release_automation.py is a module-level characterization SCRIPT
# (not pytest tests): it calls real app surfaces at import and ends with `raise SystemExit(1)` on
# failure, which silently aborts collection of every later module. Run it directly as a script
# (python tests/test_release_automation.py); it is never collected by pytest directory traversal.
collect_ignore = ["tests/test_release_automation.py"]
