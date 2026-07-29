"""Extract a valid diffusers-format LoRA adapter from a training checkpoint's
model.safetensors (which contains both base UNet weights and .lora_A.default/
.lora_B.default LoRA weights). Writes <ckpt>/pytorch_lora_weights.safetensors
in the exact format load_lora_weights() expects:
    unet.<path>.lora.down.weight / unet.<path>.lora.up.weight
Run with the .venv-gpu interpreter + PYTHONPATH to its site-packages.
"""
import sys
from pathlib import Path
from safetensors import safe_open
from safetensors.torch import save_file


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("loras/main-posts")
    steps = sys.argv[2:] or ["001072", "001608", "002144"]
    for step in steps:
        ckpt = root / f"checkpoint-{step}"
        src = ckpt / "model.safetensors"
        if not src.exists():
            print(f"SKIP {step}: {src} missing")
            continue
        out = ckpt / "pytorch_lora_weights.safetensors"
        state = {}
        with safe_open(src, framework="pt") as f:
            for k in f.keys():
                if ".lora_A.default.weight" in k:
                    new_k = "unet." + k.replace(".lora_A.default.weight", ".lora.down.weight")
                    state[new_k] = f.get_tensor(k)
                elif ".lora_B.default.weight" in k:
                    new_k = "unet." + k.replace(".lora_B.default.weight", ".lora.up.weight")
                    state[new_k] = f.get_tensor(k)
        if not state:
            print(f"SKIP {step}: no lora keys found")
            continue
        save_file(state, str(out), metadata={"format": "pt"})
        print(f"WROTE {out} ({out.stat().st_size} bytes, {len(state)} tensors)")


if __name__ == "__main__":
    main()
