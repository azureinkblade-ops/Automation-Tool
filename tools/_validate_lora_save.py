"""Validate the fixed final-save path: attach a real LoRA adapter to a UNet,
call unet.save_lora_adapter(...) exactly as train_xl_lora_folder.py now does,
and confirm a non-zero pytorch_lora_weights.safetensors results. Mirrors:
    unet.save_lora_adapter(save_directory, adapter_name='default',
                           safe_serialization=True,
                           weight_name='pytorch_lora_weights.safetensors')
"""
import os, tempfile, shutil, torch
from pathlib import Path
from diffusers import UNet2DConditionModel
from peft import LoraConfig

BASE = "models/sdxl-base"
print("loading base unet", flush=True)
unet = UNet2DConditionModel.from_pretrained(BASE, subfolder="unet",
                                            torch_dtype=torch.float16).to("cpu")
cfg = LoraConfig(r=16, lora_alpha=16, init_lora_weights="gaussian",
                 target_modules=["to_q", "to_k", "to_v", "to_out.0"])
unet.add_adapter(cfg)
print("adapter attached; saving via save_lora_adapter", flush=True)

tmp = Path(tempfile.mkdtemp(prefix="lora_validate_"))
try:
    unet.save_lora_adapter(save_directory=str(tmp), adapter_name="default",
                           safe_serialization=True,
                           weight_name="pytorch_lora_weights.safetensors")
    written = tmp / "pytorch_lora_weights.safetensors"
    assert written.exists() and written.stat().st_size > 0, "empty/0-byte file!"
    print("OK size_bytes=%d" % written.stat().st_size, flush=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("VALIDATION PASSED", flush=True)
