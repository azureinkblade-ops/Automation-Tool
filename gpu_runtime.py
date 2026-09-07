"""Minimal GPU / DLL runtime bootstrap for local SD tools.

Purpose: replace bare `import app` in model backends so subsystem CLIs do not
pull the monolith. Safe to call multiple times. No server/worker side effects.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BOOTSTRAPPED = False


def ensure_gpu_runtime() -> None:
    """Establish package + common CUDA DLL search paths without importing app.

    The GPU venv historically relied on `import app` for consistent path setup.
    This helper keeps that intent while remaining monolith-free.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    root = Path(__file__).resolve().parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Optional: surface CUDA bin dirs so torch can load its DLLs on Windows.
    candidates = []
    cuda_path = os.environ.get("CUDA_PATH") or os.environ.get("CUDA_HOME")
    if cuda_path:
        candidates.append(Path(cuda_path) / "bin")
    # Common local venv locations used by this project
    for rel in (".venv-gpu", "venv-gpu"):
        candidates.append(root / rel / "Lib" / "site-packages" / "torch" / "lib")
        candidates.append(root / rel / "Scripts")

    if hasattr(os, "add_dll_directory"):
        for path in candidates:
            try:
                if path.is_dir():
                    os.add_dll_directory(str(path))
            except (OSError, FileNotFoundError):
                pass
