#!/usr/bin/env python3
"""Generate speech with Chatterbox TTS (MIT). Designed to be invoked from the
automation tool's make_chatterbox_audio() via the isolated .venv-chatterbox python.

Usage: chatterbox_gen.py <out_wav> <text_file> [ref_wav]
Reads narration text from <text_file>, writes a single wav to <out_wav>.
Optional <ref_wav> enables zero-shot voice cloning (use a voice you own/license).
"""
import sys, os

def main():
    if len(sys.argv) < 3:
        print("usage: chatterbox_gen.py <out_wav> <text_file> [ref_wav]", file=sys.stderr)
        return 2
    out_wav = sys.argv[1]
    text_file = sys.argv[2]
    ref_wav = sys.argv[3] if len(sys.argv) > 3 else None
    with open(text_file, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print("empty text", file=sys.stderr)
        return 1

    try:
        from chatterbox import ChatterboxTTS
    except Exception as exc:
        print(f"chatterbox import failed: {exc}", file=sys.stderr)
        return 1

    # Prefer CUDA if this venv happens to have it; otherwise CPU (still works).
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        model = ChatterboxTTS.from_pretrained(device=device)
    except Exception as exc:
        print(f"chatterbox model load failed: {exc}", file=sys.stderr)
        return 1

    audio_prompt_path = ref_wav if (ref_wav and os.path.exists(ref_wav)) else None
    try:
        wav = model.generate(text, audio_prompt_path=audio_prompt_path)
        import torchaudio
        torchaudio.save(out_wav, wav, model.sr)
    except Exception as exc:
        print(f"chatterbox generate failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out_wav} ({device})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
