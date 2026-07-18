"""GPU pre-flight helper for LoRA training launchers (cross-shell: works under
bash and cmd). Prints a JSON status and exits 0 if enough free VRAM is available,
non-zero otherwise. Uses nvidia-smi (no torch/CUDA init) so it never allocates
GPU memory or disturbs other processes.

Usage:
    python check_gpu.py [min_free_gib]

Exit codes:
    0  -> GPU free VRAM >= min_free_gib (or no min required and a GPU exists)
    2  -> GPU present but not enough free VRAM
    1  -> nvidia-smi unavailable / no GPU / parse error
"""
import json
import subprocess
import sys


def main() -> int:
    min_free_gib = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.STDOUT, text=True, timeout=15,
        )
    except Exception as exc:  # nvidia-smi missing / timeout / not a GPU box
        print(json.dumps({"ok": False, "reason": f"nvidia-smi error: {exc}"}))
        return 1
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if not lines:
        print(json.dumps({"ok": False, "reason": "nvidia-smi returned no data"}))
        return 1
    try:
        free_mib, total_mib = (float(x.strip()) for x in lines[0].split(","))
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": f"nvidia-smi parse error: {exc}"}))
        return 1
    free_gib = free_mib / 1024.0
    total_gib = total_mib / 1024.0
    ok = free_gib >= min_free_gib
    print(json.dumps({
        "ok": ok,
        "free_gib": round(free_gib, 1),
        "total_gib": round(total_gib, 1),
        "min_free_gib": min_free_gib,
    }))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
