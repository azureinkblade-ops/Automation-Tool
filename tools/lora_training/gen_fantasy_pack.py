"""Generate 100 realistic generic fantasy images with the trained azink_real LoRA.
100 curated captions (20 each: elf/knight/dragon/magic/castle). Seeded for reproducibility.
Outputs azink_real_001..100.jpg + fantasy_pack_manifest.csv (index,theme,filename,caption,prompt)
to loras/realistic_posts/fantasy_pack/.
Run with Codex-bundled python + HF offline + env -u PYTHONPATH -u PYTHONHOME.
"""
import os, csv, torch
from diffusers import StableDiffusionXLPipeline

OUT = "loras/realistic_posts/fantasy_pack"
os.makedirs(OUT, exist_ok=True)
LORA = "loras/realistic_posts/pytorch_lora_weights.safetensors"
BASE = "models/sdxl-base"
N = 100
SEED = 20260713

STYLE = ("azink_real, cinematic realistic fantasy character art, highly detailed, dramatic lighting, "
         "premium digital painting, atmospheric, photorealistic fantasy render, intricate detail, "
         "cinematic composition")
NEG = ("cartoon, anime, 3d render, low quality, watermark, text, deformed, extra limbs, "
       "oversaturated, blurry, bad anatomy, duplicate, signature, logo")

# 100 curated captions, 20 per theme in order elf/knight/dragon/magic/castle
CAPTIONS = [
    # ELF (1-20)
    "Elf archer loosing a glowing arrow across a misty forest clearing",
    "Elf mage hurling a sphere of arcane fire at a shadow beast",
    "Elf queen upon a throne of living wood in a luminous grove",
    "Elf ranger perched in a treetop, drawing a bead on a distant orc",
    "Elf warrior dual-wielding curved blades amid falling leaves",
    "Elf priestess channeling healing light over a fallen comrade",
    "Elf scout creeping through bioluminescent mushroom caves",
    "Elf sorceress riding a giant stag through a starlit glade",
    "Elf blacksmith forging a silver elven blade at a glowing anvil",
    "Elf assassin vanishing into shadow beneath a moonlit bridge",
    "Elf child discovering a glowing fairy in a flower field",
    "Elf commander rallying her battalion beneath an ancient banner",
    "Elf druid shifting into a wolf under a blood-red moon",
    "Elf sailor steering a leaf-shaped boat down a glowing river",
    "Elf scholar reading a floating tome of forbidden lore",
    "Elf huntress with a falcon companion on a snowy ridge",
    "Elf guardian wielding a staff of woven light at a forest shrine",
    "Elf gladiator bloodied but unbowed in a moss-covered arena",
    "Elf musician enchanting a crowd with a singing crystal harp",
    "Elf sentinel atop a massive tree watching an approaching dragon",
    # KNIGHT (21-40)
    "Knight in shining armor charging on a warhorse through a river crossing",
    "Paladin raising a radiant sword against a tide of skeletons",
    "Knight kneeling before a king to receive a ceremonial sword",
    "Battle-worn knight resting by a campfire after a long siege",
    "Female knight with a flaming lance leading a cavalry charge",
    "Knight in tattered armor defending a village gate from raiders",
    "Templar knight praying in a candlelit stone chapel",
    "Knight dueling a rival on a cliff edge at sunset",
    "Heavy knight in full plate wading through a swamp battlefield",
    "Knight rescuing a child from a burning castle hallway",
    "Holy knight with a glowing shield repelling a dark sorcerer's bolt",
    "Knight in a tournament jousting before a cheering crowd",
    "Fallen knight lying heroically amid the ruins of a lost battle",
    "Knight scanning a horizon from a lonely watchtower",
    "Knight in ornate gilded armor presenting a banner to a queen",
    "Rogue knight with a blackened sword in a plague-stricken town",
    "Knight climbing an icy fortress wall under arrow fire",
    "Knight sharing a quiet moment with his warhorse at dawn",
    "Knight in dragon-scale armor standing victorious on a hill",
    "Knight meditating with a sword planted in stone",
    # DRAGON (41-60)
    "Red dragon breathing a torrent of fire over a mountain pass",
    "Ice dragon coiled atop a frozen peak under the aurora",
    "Dragon hatchling nuzzling a treasure hoard of gold coins",
    "Black dragon rising from a misty volcanic lake",
    "Golden dragon soaring above a sea of clouds at sunrise",
    "Dragon battling a knight in mid-air over a crumbling bridge",
    "Amethyst dragon guarding an egg in a crystal cavern",
    "Storm dragon whipping lightning across a thunderhead",
    "Ancient dragon sleeping atop a pile of ancient relics",
    "Forest dragon with leafy wings perched in a giant oak",
    "Shadow dragon phasing through a castle wall at midnight",
    "Dragon wyrmling learning to fly above a meadow",
    "Brass dragon laughing amid a bazaar of merchants",
    "Dragon of bone and ash prowling a dead wasteland",
    "Celestial dragon weaving constellations in the night sky",
    "Dragon and phoenix locked in a blaze of feathers and flame",
    "Water dragon surfacing in a moonlit harbor",
    "Dragon curled protectively around a sleeping elf child",
    "Two-headed dragon roaring over a divided kingdom",
    "Dragon silhouette against a blood moon on the horizon",
    # MAGIC (61-80)
    "Sorcerer opening a swirling portal of violet energy",
    "Witch peering into a crystal orb showing a distant storm",
    "Wizard inscribing glowing runes on a stone floor circle",
    "Mage sculpting a golem of living clay in a workshop",
    "Enchantress weaving threads of starlight into a cloak",
    "Alchemist mixing a glowing potion that erupts in sparks",
    "Necromancer raising a skeletal hand from the grave soil",
    "Druid calling vines to entangle a ruined temple",
    "Time mage freezing a falling droplet mid-air with a gesture",
    "Illusionist conjuring a mirror maze of light",
    "Storm caller summoning a tornado over a helpless village",
    "Fire dancer spinning wisps of flame into a phoenix shape",
    "Seer reading fate in a spread of floating tarot cards",
    "Battle mage shielding allies with a dome of shimmering force",
    "Rune smith branding a glowing sigil onto a steel shield",
    "Star witch bathing in a waterfall of falling comets",
    "Shadow weaver stitching darkness into a living cloak",
    "Elementalist balancing fire, water, earth, and air orbs",
    "Oracle channeling a ghostly ancestor through a veil",
    "Spell thief stealing magic from a trapped demon's cage",
    # CASTLE (81-100)
    "Stone castle on a cliff at sunset with banners snapping in wind",
    "Snowbound fortress citadel glowing warm in a mountain pass",
    "Ruined castle overgrown with ivy at the break of dawn",
    "Floating castle among clouds with waterfalls spilling off edges",
    "Coastal castle on a rocky isle lashed by ocean waves",
    "Desert palace of white stone beneath a blazing noon sun",
    "Hidden castle concealed within a ring of ancient trees",
    "War-torn castle with scorched walls and broken gates",
    "Crystal castle shimmering in a cavern of glowing gems",
    "Castle bridge spanning a chasm over a roaring waterfall",
    "Obsidian fortress pulsing with veins of red magma",
    "Riverside castle reflected perfectly in a still moat",
    "Mountain keep wrapped in storm clouds and lightning",
    "Elven tree-castle grown from a colossal living trunk",
    "Underwater dome castle glowing in the deep sea",
    "Castle marketplace bustling with merchants at festival",
    "Abandoned castle crypt with a single shaft of moonlight",
    "Golden palace of a dragon lord atop a conquered peak",
    "Castle observatory with a telescope aimed at a comet",
    "Tiny castle on a hill surrounded by a ring of standing stones",
]
assert len(CAPTIONS) == N, len(CAPTIONS)
THEMES = (["elf"]*20 + ["knight"]*20 + ["dragon"]*20 + ["magic"]*20 + ["castle"]*20)

print("Loading pipeline...")
pipe = StableDiffusionXLPipeline.from_pretrained(BASE, torch_dtype=torch.float16, use_safetensors=True, variant="fp16").to("cuda")
pipe.load_lora_weights(LORA, weight_name="pytorch_lora_weights.safetensors")
pipe.set_progress_bar_config(disable=True)
print("LoRA loaded.")

rows = []
for i, cap in enumerate(CAPTIONS, start=1):
    theme = THEMES[i-1]
    prompt = f"{STYLE}, {cap}"
    gen = torch.Generator(device="cuda").manual_seed(SEED + i)
    img = pipe(prompt, negative_prompt=NEG, num_inference_steps=30, guidance_scale=7.5,
               width=1024, height=1024, num_images_per_prompt=1, generator=gen).images[0]
    fname = f"azink_real_{i:03d}.jpg"
    img.save(os.path.join(OUT, fname), quality=88)
    rows.append((i, theme, fname, cap, prompt))
    if i % 10 == 0 or i == 1:
        print(f"  {i}/{N} done ({theme})", flush=True)

with open(os.path.join(OUT, "fantasy_pack_manifest.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["index", "theme", "filename", "caption", "prompt"])
    for r in rows:
        w.writerow(r)
print(f"DONE: {N} images + manifest in {OUT}")
