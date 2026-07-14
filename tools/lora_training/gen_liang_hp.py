import torch
from diffusers import StableDiffusionXLPipeline

pipe = StableDiffusionXLPipeline.from_pretrained(
    "models/sdxl-base", torch_dtype=torch.float16, use_safetensors=True, variant="fp16"
).to("cuda")
pipe.load_lora_weights("loras/realistic_posts/pytorch_lora_weights.safetensors",
                        weight_name="pytorch_lora_weights.safetensors")
pipe.set_progress_bar_config(disable=True)
print("LoRA loaded (Liang HP)", flush=True)

# Liang — Hundredfold Path: classical xianxia, reborn sect cultivator, jade token, mountain sect, silver weapon, qi core
prompt = ("azink_real, cinematic realistic classical xianxia character portrait, "
          "young man in deep JADE-AND-WHITE sect robes with a glowing JADE TOKEN hanging at his belt, "
          "calm expression, a SILVER-EDGED SWORD resting prominently at his side, BRIGHT FAINT GOLDEN QI LIGHT glowing at his core and hands, "
          "misty mountain sect with curved rooftops and RED RISING BANNERS behind him, frost in the air, premium web novel character art")
neg = "cartoon, anime, 3d render, cyberpunk, modern clothing, no weapon, no glow, low quality, watermark, text, deformed, extra limbs"

out = pipe(prompt, negative_prompt=neg, num_inference_steps=40, guidance_scale=9.0,
           width=1024, height=1024, num_images_per_prompt=1).images[0]
out.save("loras/realistic_posts/test_liang_hp.png")
print("SAVED loras/realistic_posts/test_liang_hp.png", flush=True)
