import torch
from diffusers import StableDiffusionXLPipeline

pipe = StableDiffusionXLPipeline.from_pretrained(
    "models/sdxl-base", torch_dtype=torch.float16, use_safetensors=True, variant="fp16"
).to("cuda")
pipe.load_lora_weights("loras/realistic_posts/pytorch_lora_weights.safetensors",
                        weight_name="pytorch_lora_weights.safetensors")
pipe.set_progress_bar_config(disable=True)
print("LoRA loaded (Kael EN)", flush=True)

# Kael Veyra — Eternal Nexus: cyberpunk LitRPG, NexusPod, blue glyphs, Soulblade
prompt = ("azink_real, cinematic realistic cyberpunk LitRPG character portrait, "
          "young man with sharp features and dark hair, wearing a sleek dark jacket with BRIGHT glowing blue circuit glyphs across the chest and arms, "
          "standing indoors in a dim neon apartment at night before a tall OBSIDIAN NEXUSPOD shell etched with glowing blue runes, "
          "HOLDING A CONDENSED ECLIPSE SOULBLADE of swirling dark energy in his fist, holographic blue UI glow, premium web novel character art")
neg = "cartoon, anime, 3d render, wuxia robe, fantasy armor, outdoors, street, no weapon, low quality, watermark, text, deformed, extra limbs"

out = pipe(prompt, negative_prompt=neg, num_inference_steps=40, guidance_scale=9.0,
           width=1024, height=1024, num_images_per_prompt=1).images[0]
out.save("loras/realistic_posts/test_kael_en.png")
print("SAVED loras/realistic_posts/test_kael_en.png", flush=True)
