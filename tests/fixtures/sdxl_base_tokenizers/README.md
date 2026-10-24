# sdxl_base_tokenizers (Linux CI)

Place CLIP-L and CLIP-G **tokenizer-only** folders here (no UNet/VAE/text_encoder weights):

- `tokenizer/vocab.json` + `tokenizer/merges.txt` (+ tokenizer_config.json)
- `tokenizer_2/vocab.json` + `tokenizer_2/merges.txt` (+ tokenizer_config.json)

Resolved by `tools.local_sdxl_compact_prompt.resolve_tokenizer_dirs` after `models/sdxl-base`. If absent, tests marked `requires_sdxl_tokenizer` SKIP (never silent pass).
