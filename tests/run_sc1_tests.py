"""Minimal test runner for SC-1 storage manifest tests.

Avoids a pytest dependency. Runs every test_* function in
tests/test_storage_manifest.py and reports pass/fail counts. Read-only.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "tests"
SPEC_FILES = sorted(SPEC_DIR.glob("test_storage_*.py"))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_module(path: Path):
    name = path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    passed = 0
    failed = 0
    notes = []
    for spec_path in SPEC_FILES:
        mod = load_module(spec_path)
        tests = [getattr(mod, n) for n in dir(mod) if n.startswith("test_") and callable(getattr(mod, n))]
        for t in tests:
            try:
                extra = t()
                if isinstance(extra, list):
                    notes.append(f"{spec_path.name}:{t.__name__}: {len(extra)} unresolved/unknown")
            except Exception:
                failed += 1
                print(f"FAIL {spec_path.name}:{t.__name__}")
                traceback.print_exc()
            else:
                passed += 1
                print(f"PASS {spec_path.name}:{t.__name__}")
    print(f"\nStorage tests: {passed} passed, {failed} failed, {passed + failed} total")
    for n in notes:
        print(f"  note: {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
