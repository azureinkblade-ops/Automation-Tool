"""Generate promo thumbnail (square) + cover/banner (wide) for the Fantasy Image Pack.
Uses the trained azink_real LoRA. Saved to Sales/ as promo assets.
Run with Codex-bundled python + HF offline + env -u PYTHONPATH -u PYTHONHOME.
"""
import os, torch
from diffusers import StableDiffusionXLPipeline

SALES = r"C:\Users\David\Documents\Sales"
LORA = "loras/realistic_posts/pytorch_lora_weights.safetensors"
BASE = "models/sdxl-base"
SEED = 20260713

STYLE = ("azink_real, cinematic realistic fantasy key art, highly detailed, dramatic lighting, "
         "premium digital painting, atmospheric, photorealistic fantasy render, intricate detail")
NEG = ("cartoon, anime, 3d render, low quality, watermark, text, deformed, extra limbs, "
       "oversaturated, blurry, bad anatomy, duplicate, signature, logo, words")

pipe = StableDiffusionXLPipeline.from_pretrained(BASE, torch_dtype=torch.float16, use_safetensors=True, variant="fp16").to("cuda")
pipe.load_lora_weights(LORA, weight_name="pytorch_lora_weights.safetensors")
pipe.set_progress_bar_config(disable=True)

# THUMBNAIL: square hero — a majestic dragon + castle silhouette, centered, bold readable
thumb_prompt = (f"{STYLE}, a majestic armored knight standing before a towering stone castle on a cliff at "
                f"sunset, a great red dragon soaring across the orange sky above, banners flying, "
                f"epic composition with clear central subject and negative space for text overlay")
thumb = pipe(thumb_prompt, negative_prompt=NEG, num_inference_steps=35, guidance_scale=7.5,
             width=1024, height=1024, generator=torch.Generator(device="cuda").manual_seed(SEED+1)).images[0]
thumb.save(os.path.join(SALES, "fantasy_pack_thumbnail.jpg"), quality=92)
print("thumbnail saved")

# COVER/BANNER: wide 1600x900 — elf + knight + dragon + castle montage feel, cinematic
cover_prompt = (f"{STYLE}, epic fantasy panorama: an elf archer on a misty forest left, a holy knight with a "
                f"glowing sword center, a massive dragon rising over a mountain castle right, golden hour "
                f"light, grand scale, balanced composition with room for title text at top")
cover = pipe(cover_prompt, negative_prompt=NEG, num_inference_steps=35, guidance_scale=7.5,
             width=1600, height=896, generator=torch.Generator(device="cuda").manual_seed(SEED+2)).images[0]
cover.save(os.path.join(SALES, "fantasy_pack_cover.jpg"), quality=92)
print("cover saved")
print("DONE promo images")
