import torch
from diffusers import StableDiffusionXLPipeline

pipe = StableDiffusionXLPipeline.from_pretrained(
    "models/sdxl-base", torch_dtype=torch.float16, use_safetensors=True, variant="fp16"
).to("cuda")

lora = "loras/realistic_posts/pytorch_lora_weights.safetensors"
pipe.load_lora_weights(lora, weight_name="pytorch_lora_weights.safetensors")
pipe.set_progress_bar_config(disable=True)
print("LoRA loaded:", lora, flush=True)

prompt = ("azink_real, cinematic realistic cyberpunk mystic, east asian male with long black high ponytail "
          "and sharp features, glowing gold tattoos on face and hand, dark heavy robe, extending a hand toward "
          "a futuristic egg-shaped command chair with golden lightning from his fingertips, dim high-tech room "
          "with neon cyberpunk city window behind and holographic interface, medium shot, cool blue city against "
          "warm gold energy, technological mysticism mood, premium web novel character art")
neg = "cartoon, anime, 3d render, low quality, watermark, text, deformed, extra limbs"

out = pipe(prompt, negative_prompt=neg, num_inference_steps=30, guidance_scale=7.5,
           width=1024, height=1024, num_images_per_prompt=1).images[0]
out.save("loras/realistic_posts/test_kael.png")
print("SAVED loras/realistic_posts/test_kael.png", flush=True)
