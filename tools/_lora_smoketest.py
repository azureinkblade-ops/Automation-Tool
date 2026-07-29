import os, sys, torch
from pathlib import Path
from diffusers import StableDiffusionXLPipeline

BASE = "models/sdxl-base"
LORA = Path(sys.argv[1])
print("loading base", flush=True)
pipe = StableDiffusionXLPipeline.from_pretrained(
    BASE, torch_dtype=torch.float16, use_safetensors=True, variant="fp16").to("cuda")
print("base loaded; loading lora", flush=True)
pipe.load_lora_weights(str(LORA.parent), weight_name=LORA.name)
print("lora loaded OK:", LORA, flush=True)
prompt = ("azink_main, vertical heroic web novel promotional cover art, lone martial cultivator "
          "standing on temple steps during a fire trial, burning braziers, ruined sacred hall")
neg = ("cartoon, anime, 3d render, low quality, watermark, text, deformed, extra limbs, "
       "oversaturated, blurry, bad anatomy, duplicate, signature, logo, words")
print("generating test image", flush=True)
img = pipe(prompt, negative_prompt=neg, num_inference_steps=30, guidance_scale=7.5,
           width=1024, height=1024,
           generator=torch.Generator(device="cuda").manual_seed(1234)).images[0]
out = Path("loras/main-posts/eval-grid/_smoketest.png")
out.parent.mkdir(parents=True, exist_ok=True)
img.save(str(out))
print("SMOKE OK ->", out, flush=True)
