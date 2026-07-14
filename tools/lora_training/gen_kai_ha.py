import torch
from diffusers import StableDiffusionXLPipeline

pipe = StableDiffusionXLPipeline.from_pretrained(
    "models/sdxl-base", torch_dtype=torch.float16, use_safetensors=True, variant="fp16"
).to("cuda")
pipe.load_lora_weights("loras/realistic_posts/pytorch_lora_weights.safetensors",
                        weight_name="pytorch_lora_weights.safetensors")
pipe.set_progress_bar_config(disable=True)
print("LoRA loaded", flush=True)

# Kai from Heavenly Ascension System (Ch.1): 19yo sickly convenience-store clerk,
# gray shirt w/ faded logo + black pants, warm golden ember glow at chest, Qi threads,
# rainy neon city, pale-blue floating system panel.
prompt = ("azink_real, cinematic realistic modern cultivation character portrait, "
          "young man about 19 with thin pale features and short dark hair, "
          "wearing a gray convenience store shirt with a faded logo and black pants, "
          "BRIGHT WARM GOLDEN EMBER GLOW erupting from his chest beneath his ribs, "
          "glowing amber qi energy threads swirling visibly around his torso and hands, "
          "a glowing pale-blue translucent holographic system interface panel floating in the air beside him with faint lines of text, "
          "rainy neon-lit city street behind him, sickly yet awakening, premium web novel character art")
neg = "cartoon, anime, 3d render, wuxia robe, fantasy armor, low quality, watermark, deformed, extra limbs, dim, no glow"

out = pipe(prompt, negative_prompt=neg, num_inference_steps=35, guidance_scale=8.5,
           width=1024, height=1024, num_images_per_prompt=1).images[0]
out.save("loras/realistic_posts/test_kai_ha.png")
print("SAVED loras/realistic_posts/test_kai_ha.png", flush=True)
