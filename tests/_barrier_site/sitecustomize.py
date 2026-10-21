# PYTEST_LIVE_SIDE_EFFECT_ISOLATION: installs the live side-effect barrier in every
# Python child process spawned from a barriered pytest run (PYTHONPATH injection).
import os as _os
import sys as _sys

if _os.environ.get("AT_GPU_TEST_BARRIER") == "1" and _os.environ.get("AT_LIVE_BARRIER_ROOT"):
    _here = _os.path.dirname(_os.path.abspath(__file__))
    _repo = _os.path.dirname(_os.path.dirname(_here))
    if _repo not in _sys.path:
        _sys.path.append(_repo)
    try:
        import importlib.util as _u
        _spec = _u.spec_from_file_location(
            "tests.live_side_effect_barrier",
            _os.path.join(_os.path.dirname(_here), "live_side_effect_barrier.py"),
        )
        _mod = _u.module_from_spec(_spec)
        _sys.modules["tests.live_side_effect_barrier"] = _mod
        _spec.loader.exec_module(_mod)
        _mod.install(child=True)
    except SystemExit:
        raise
    except BaseException as _exc:  # fail closed: a child that cannot install must not run
        _sys.stderr.write(f"LIVE_BARRIER_CHILD_INSTALL_FAILED: {_exc!r}\n")
        _os._exit(97)
