"""Introspect the live execution environment for the reproducible-execution bundle.

Run with the same interpreter used for the actual V1 run:
    .venv-gpu/Scripts/python.exe tests/render_ab/introspect_stage2_v1_env.py
Emits a JSON blob of versions / GPU / file hashes that the bundle generator
records. Kept separate from the bundle itself so re-running it is cheap.
"""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=120
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"<error: {exc}>"


def main() -> int:
    info: dict = {}
    info["python_version"] = sys.version.split()[0]

    # package versions via importlib.metadata (no C-extension import needed,
    # avoids the broken torch DLL that triggers on a bare `import torch`)
    pkgs = {}
    for name in ("torch", "diffusers", "pillow", "numpy", "transformers", "controlnet-aux", "huggingface-hub"):
        try:
            from importlib.metadata import version
            pkgs[name] = version(name)
        except Exception as exc:  # noqa: BLE001
            pkgs[name] = f"<unavailable: {type(exc).__name__}>"
    info["packages"] = pkgs

    # GPU name recorded from the backend's real environment at run time is
    # preferable; here we capture it lazily only if torch loads without the DLL
    # error, else leave null (the execution records already carry model/seed/
    # parameters as the authoritative generation config).
    info["interpreter"] = sys.executable
    try:
        import torch  # may raise OSError on this host's broken DLL
        info["cuda_available"] = torch.cuda.is_available()
        info["gpu_name"] = (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        )
    except Exception as exc:  # noqa: BLE001
        info["gpu_note"] = (
            f"torch import raised {type(exc).__name__} in this introspection "
            "context; GPU name not captured here. The V1 run itself imported "
            "torch successfully via the same interpreter to generate candidates."
        )

    # git
    info["git_head"] = run(["git", "rev-parse", "HEAD"])
    # record a hash of the working-tree diff (dirty state) if any
    diff = run(["git", "diff", "--", "app.py", "local_image_generator.py",
                "tests/render_ab/harness.py", "tests/render_ab/run_real_ab.py"])
    info["git_dirty_tree_diff_sha256"] = sha256_digest(diff.encode()) if diff else None
    info["git_status_porcelain_len"] = len(run(["git", "status", "--porcelain"]).splitlines())

    # model + lora file hashes (what the backend actually loaded)
    info["model_files"] = {
        "sdxl_base": sha256(ROOT / "models/sdxl-base/sd_xl_base_1.0.safetensors"),
        "lora_azink_main": sha256(ROOT / "loras/main-posts/pytorch_lora_weights.safetensors"),
    }

    print(json.dumps(info, indent=2))
    return 0


def sha256_digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
