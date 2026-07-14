import torch
from diffusers import StableDiffusionXLPipeline

pipe = StableDiffusionXLPipeline.from_pretrained(
    "models/sdxl-base", torch_dtype=torch.float16, use_safetensors=True, variant="fp16"
).to("cuda")
pipe.load_lora_weights("loras/realistic_posts/pytorch_lora_weights.safetensors",
                        weight_name="pytorch_lora_weights.safetensors")
pipe.set_progress_bar_config(disable=True)
print("LoRA loaded (Jarek SF)", flush=True)

# Jarek — Soulforge Era: undercity scavenger, gold eyes, iron chains, forge-fire, ruined ring-city
prompt = ("azink_real, cinematic realistic post-apocalyptic soulforge character portrait, "
          "young man with rough scavenger clothes and soot-streaked face, BRIGHT GLOWING GOLD EYES, "
          "HEAVY IRON CHAINS COILED TIGHTLY AROUND BOTH ARMS, warm forge-fire and floating embers lighting his skin, "
          "collapsed undercity rail tunnel with rust and old rain, a burning ring-city silhouette glowing far above through the gap, premium web novel character art")
neg = "cartoon, anime, 3d render, wuxia robe, fantasy armor, clean, normal eyes, no chains, low quality, watermark, text, deformed, extra limbs"

out = pipe(prompt, negative_prompt=neg, num_inference_steps=40, guidance_scale=9.0,
           width=1024, height=1024, num_images_per_prompt=1).images[0]
out.save("loras/realistic_posts/test_jarek_sf.png")
print("SAVED loras/realistic_posts/test_jarek_sf.png", flush=True)
