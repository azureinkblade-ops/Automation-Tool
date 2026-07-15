# azink_main LoRA — Training Recipe (reuses azink_real baseline)

Track: `main-posts` · Trigger: `azink_main`
Use: Daily chapter promos, Patreon/X/Facebook images, general novel campaign art.

## Baseline (captured from azink_real — proven on RTX 4080 SUPER 16GB)
- pretrained_model: `models/sdxl-base` (full SDXL diffusers layout: unet / text_encoder / text_encoder_2 / vae)
- resolution: 1024 (square, center-crop from source)
- train_batch_size: 1
- gradient_accumulation_steps: 4
- learning_rate: 1e-4
- num_train_epochs: 12
- max_train_steps: 0 (use epochs)
- rank: 16 (lora_alpha = rank)
- seed: 42
- mixed_precision: bf16
- repeats: 10 (dataset duplicated 10x per epoch)
- shuffle_tags: false

## Trainer
`tools/lora_training/train_xl_lora_folder.py`
Reads `<img>.<ext>` + `<img>.txt` pairs from `--train_data_dir`.
Output: `<output_dir>/pytorch_lora_weights.safetensors`.

## Dataset (prepared by tools/lora_training/prepare_main_posts_dataset.py)
`lora-training/main-posts/datasets/train-1024/` — 119 image+caption pairs:
- 15 curated from `approved/` (captions copied from `captions/`)
- 104 keyframes from `campaigns/` + `tiktok-posts/` chapters 19-25, NON-deep
  (filenames EN_/HA_/HP_/SF_ only). Excludes reel/animated, promo-cards, and
  any 'other' bucket to avoid Pexels-stock / text-overlay contamination.

## Launch command
```
python tools/lora_training/train_xl_lora_folder.py ^
  --pretrained_model models/sdxl-base ^
  --train_data_dir lora-training/main-posts/datasets/train-1024 ^
  --output_dir loras/main-posts ^
  --resolution 1024 --train_batch_size 1 --gradient_accumulation_steps 4 ^
  --learning_rate 0.0001 --num_train_epochs 12 --rank 16 --seed 42 ^
  --mixed_precision bf16 --repeats 10
```
Output lands in `loras/main-posts/pytorch_lora_weights.safetensors` (the app's
`LORA_STYLE_TRACKS["main-posts"]` target).

## Operational guard
- Run ONLY when the app server + diffusers/ffmpeg workers are stopped (VRAM contention).
- ~119 pairs x repeats 10 = ~1190 samples/epoch x 12 epochs. On 16GB this is a
  multi-hour GPU job — launch background + notify, do not block.
- Optional tuning: if RAM/VRAM spikes, set MAX_CONCURRENT_HEAVY_JOBS=1 (N/A during training).
