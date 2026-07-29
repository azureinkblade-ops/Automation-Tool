import sys
from safetensors import safe_open

p = sys.argv[1]
with safe_open(p, framework="pt") as f:
    ks = list(f.keys())
lora = [k for k in ks if "lora" in k.lower()]
# show top-level module prefixes of lora keys
prefixes = {}
for k in lora:
    top = k.split(".")[0]
    prefixes[top] = prefixes.get(top, 0) + 1
print("LORA_TOP_PREFIXES", prefixes)
# any text encoder lora?
te = [k for k in lora if "text_encoder" in k.lower()]
print("TEXT_ENCODER_LORA_COUNT", len(te))
for k in te[:4]:
    print("TE", k)
# sample unet lora key transform check
sample = [k for k in lora if k.startswith("down_blocks")][:2]
for k in sample:
    print("RAW", k)
