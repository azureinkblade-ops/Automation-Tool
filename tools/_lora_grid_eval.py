"""Side-by-side LoRA checkpoint evaluation for main-posts (azink_main).

For each candidate checkpoint, generate the SAME fixed prompts at the SAME seed
so the only variable is the trained checkpoint. Also render a no-LoRA baseline.
Produces one grid PNG per prompt (rows = checkpoints, 1 col) plus a 2x2 contact
sheet per checkpoint, saved under loras/main-posts/eval-grid/.

Mirrors production generation: SDXL base fp16, load_lora_weights(weight_name=...),
35 steps, cfg 7.5, vertical 1024x1536, the standard negative prompt, and the
azink_main trigger + promptSuffix exactly as enhance_local_sd_prompt assembles it.
"""
import os
import torch
from pathlib import Path
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageDraw

ROOT = Path("loras/main-posts")
GRID = ROOT / "eval-grid"
GRID.mkdir(parents=True, exist_ok=True)

BASE = "models/sdxl-base"
TRIGGER = "azink_main"
SUFFIX = ("Azure Inkblade chapter promo art, strong web novel cover composition, "
          "high-impact social media framing, vertical 9:16 promotional illustration, "
          "polished digital painting, dramatic lighting, clear focal character")
NEG = ("cartoon, anime, 3d render, low quality, watermark, text, deformed, extra limbs, "
       "oversaturated, blurry, bad anatomy, duplicate, signature, logo, words")

# Fixed prompts — one per novel flavor (EN heroic duo, HA fire-cultivator, SF paladin, HP scenic)
PROMPTS = {
    "EN": "azink_main, vertical heroic web novel promotional cover art, dynamic fantasy adventurer duo in an ancient golden temple, armored male warrior and agile female blade fighter, glowing celestial spirit above, dramatic upward composition, action pose, warm divine lighting, polished digital illustration, high-impact social media fantasy poster",
    "HA": "azink_main, vertical fantasy web novel promotional cover art, lone martial cultivator standing on temple steps during a fire trial, burning braziers, ruined sacred hall, orange flames, determined central character, dramatic symmetrical composition, cinematic lighting, polished painterly illustration, high-impact chapter promo image",
    "SF": "azink_main, vertical heroic web novel promotional cover art, white-haired celestial paladin in ornate gold and white armor holding a sword, glowing halo and divine cross above, temple columns, blue and gold magic light, confident central character, elegant polished digital illustration, premium chapter promo poster",
    "HP": "azink_main, vertical scenic web novel promotional landscape, ancient giant trees forming a natural archway, solitary tiny cloaked traveler ascending stone stairs toward bright golden light, lush green forest with purple flowers, weathered stone gateposts, rolling hills and valley behind, sunrise through clouds, symmetrical leading-line composition, ethereal storybook lighting, polished digital illustration, high-impact social media fantasy poster",
}

CKPTS = {
    "baseline": None,            # no LoRA
    "ckpt-001072": "checkpoint-001072/pytorch_lora_weights.safetensors",
    "ckpt-001608": "checkpoint-001608/pytorch_lora_weights.safetensors",
    "ckpt-002144": "checkpoint-002144/pytorch_lora_weights.safetensors",
}

SEED = 20260720
STEPS = 30
CFG = 7.5
W, H = 832, 1216


def label(img, text, h=64):
    """Draw a label bar at the bottom of the image."""
    base = img.convert("RGB")
    canvas = Image.new("RGB", (base.width, base.height + h), (20, 20, 20))
    canvas.paste(base, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((12, base.height + 14), text, fill=(235, 235, 235))
    return canvas


def main():
    print("loading base pipeline", flush=True)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        BASE, torch_dtype=torch.float16, use_safetensors=True, variant="fp16").to("cuda")
    pipe.set_progress_bar_config(disable=True)

    for pname, prompt in PROMPTS.items():
        full_prompt = f"{prompt}. {SUFFIX}" if SUFFIX not in prompt else prompt
        row_imgs = []
        per_ckpt_grid = []
        for cname, rel in CKPTS.items():
            if rel is None:
                print(f"[{pname}] {cname} (no lora)", flush=True)
                pipe.unload_lora_weights() if hasattr(pipe, "unload_lora_weights") else None
            else:
                lpath = ROOT / rel
                print(f"[{pname}] {cname} <- {lpath}", flush=True)
                pipe.load_lora_weights(str(lpath.parent), weight_name=lpath.name)
            g = torch.Generator(device="cuda").manual_seed(SEED)
            img = pipe(full_prompt, negative_prompt=NEG, num_inference_steps=STEPS,
                       guidance_scale=CFG, width=W, height=H, generator=g).images[0]
            limg = label(img, cname)
            row_imgs.append(limg)
            per_ckpt_grid.append((cname, img))
        # vertical stack: each prompt's checkpoints as rows
        widths = [im.width for im in row_imgs]
        heights = [im.height for im in row_imgs]
        stack = Image.new("RGB", (max(widths), sum(heights)), (0, 0, 0))
        y = 0
        for im in row_imgs:
            stack.paste(im, (0, y)); y += im.height
        out = GRID / f"grid_{pname}.png"
        stack.save(str(out))
        print("  ->", out, flush=True)
    print("DONE grids", flush=True)


if __name__ == "__main__":
    main()
