"""
Minimal SDXL LoRA training launcher for local image+caption folders.
No `datasets` dependency: reads image.jpg + image.txt pairs from --train_data_dir.
Target: RTX 4080 SUPER (16GB) -- bf16, bs=1, rank=16, 1024x1024, 8bit AdamW, grad ckpt.

NOTE: latents + text embeds were recomputed every step (no latent cache) historically
(see Workstream C diagnosis 2026-07-16); a latent+embed cache was added so the
per-step cost is now UNet-only (~1.6-2s/step), not ~20s.

STARTUP NOTE (2026-07-18): the silent "dies at model load, no error in log tail"
failure (2026-07-17/18) was caused by a foreign numpy (Hermes-agent venv's
numpy 2.4.3, cp312-built) leaking onto sys.path and breaking .venv-gpu's
torch import with "No module named 'numpy._core._multiarray_umath'". The
DEFINITIVE fix is at LAUNCH time: run with `env -u PYTHONPATH -u PYTHONHOME`
so the agent shell's env cannot seed the foreign site-packages. (A sys.path
scrub inside the script was attempted but broke stdlib import, so it is NOT
done here -- the launch-time env strip is the working defense.) This script
also pops the env vars as belt-and-suspenders, but the launch method is
what actually matters.

RESUME / MANIFEST (2026-07-18, Option B): training now checkpoints the full
Accelerate state (model + optimizer + scheduler + step) every --checkpointing_steps
steps and/or --checkpointing_epochs epochs, and writes a progress manifest JSON
(--manifest, default <output_dir>/training_manifest.json) recording stage, latest
checkpoint, global step, completed epochs, timestamps, status, and last error.
Pass --resume_from_checkpoint latest (or an explicit checkpoint dir) to continue
from the last checkpoint instead of epoch 0. Interruption is safe: the wrapper
restarts and resumes automatically.
"""
import os
# Belt-and-suspenders: drop env vars that could seed a foreign site-packages.
# (The real fix is launching with `env -u PYTHONPATH -u PYTHONHOME`.)
os.environ.pop("PYTHONPATH", None)
os.environ.pop("PYTHONHOME", None)
os.environ["PYTHONNOUSERSITE"] = "1"

import argparse
import glob
import json
import random
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from accelerate import Accelerator
from transformers import CLIPTokenizer, CLIPTextModel
from diffusers import (
    StableDiffusionXLPipeline, AutoencoderKL, UNet2DConditionModel,
    DDPMScheduler, DPMSolverMultistepScheduler,
)
from diffusers.loaders import LoraLoaderMixin
from diffusers.utils import convert_state_dict_to_diffusers
from peft import LoraConfig  # may be bundled with diffusers; fall back below if missing

import PIL.Image as Image


# ---------------------------------------------------------------------------
# Progress manifest helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mono() -> float:
    return time.monotonic()


def load_manifest(path: str) -> dict:
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_manifest(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Atomic write: temp file + rename so a kill mid-write never truncates it.
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)
    except Exception as exc:  # never let manifest I/O abort training
        print(f"[manifest] WARNING could not write {path}: {exc}", flush=True)


def find_latest_checkpoint(output_dir: str):
    """Return the checkpoint dir with the highest global_step, or None."""
    base = Path(output_dir)
    if not base.exists():
        return None
    best = None
    best_step = -1
    for d in base.glob("checkpoint-*"):
        if not d.is_dir():
            continue
        m = re.match(r"checkpoint-(\d+)$", d.name)
        if not m:
            continue
        step = int(m.group(1))
        if step > best_step:
            best_step = step
            best = d
    return best


class FolderDataset(Dataset):
    def __init__(self, root, tokenizer_one, tokenizer_two, vae, text_encoder_one,
                 text_encoder_two, device, size=1024, repeats=1, shuffle_tags=False,
                 cache_file=None):
        self.root = root
        self.tokenizer_one = tokenizer_one
        self.tokenizer_two = tokenizer_two
        self.vae = vae
        self.text_encoder_one = text_encoder_one
        self.text_encoder_two = text_encoder_two
        self.device = device
        self.size = size
        self.shuffle_tags = shuffle_tags
        self.repeats = repeats
        if cache_file is None:
            cache_file = os.path.join(root, ".latent_cache.pt")
        self.cache_file = cache_file
        pairs = []
        for p in sorted(glob.glob(os.path.join(root, "*"))):
            if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                cap = os.path.splitext(p)[0] + ".txt"
                if os.path.exists(cap):
                    pairs.append((p, cap))
        self.pairs = pairs * repeats
        # Latent + text-embed cache: encode every unique image/caption ONCE on the
        # GPU (fp32) instead of every step. This is the missing optimization that made
        # the Jul-13 realistic run ~1.6s/step vs ~51s/step without it.
        # Disk cache: persist the encoded tensors so future launches skip the
        # (slow) re-encode. Keyed by a signature of the dataset so a changed
        # dataset forces a rebuild.
        self.cache = []
        if self._try_load_cache():
            return
        _t0 = _mono()
        _n = len(self.pairs)
        for _i, (img_path, cap_path) in enumerate(self.pairs):
            image = Image.open(img_path).convert("RGB")
            if image.size != (self.size, self.size):
                image = image.resize((self.size, self.size), Image.LANCZOS)
            import torchvision.transforms as T
            pixel = T.ToTensor()(image).mul_(2).sub_(1)
            with open(cap_path, "r", encoding="utf-8") as f:
                caption = f.read().strip()
            if self.shuffle_tags:
                parts = [t.strip() for t in caption.split(",")]
                random.shuffle(parts)
                caption = ", ".join(parts)
            tok_one = self.tokenizer_one(caption, max_length=self.tokenizer_one.model_max_length,
                                         padding="max_length", truncation=True, return_tensors="pt")
            tok_two = self.tokenizer_two(caption, max_length=self.tokenizer_two.model_max_length,
                                         padding="max_length", truncation=True, return_tensors="pt")
            ids1 = tok_one.input_ids.squeeze(0)
            ids2 = tok_two.input_ids.squeeze(0)
            with torch.no_grad():
                latent = self.vae.encode(
                    pixel.unsqueeze(0).to(self.device, dtype=torch.float32)
                ).latent_dist.sample().to(torch.float32) * 0.18215
                enc1 = self.text_encoder_one(ids1.unsqueeze(0).to(self.device), output_hidden_states=True)
                enc2 = self.text_encoder_two(ids2.unsqueeze(0).to(self.device), output_hidden_states=True)
                pooled = enc2[0]
                hidden = torch.cat([enc1.hidden_states[-2], enc2.hidden_states[-2]], dim=-1)
            self.cache.append({
                "latents": latent.squeeze(0).cpu(),
                "hidden": hidden.squeeze(0).cpu(),
                "pooled": pooled.squeeze(0).cpu(),
            })
            # Progress logging so long precompute phases are observable.
            if (_i + 1) % 25 == 0 or (_i + 1) == _n:
                _el = _mono() - _t0
                _rate = (_i + 1) / _el if _el > 0 else 0.0
                _eta = (_n - (_i + 1)) / _rate if _rate > 0 else 0.0
                print(f"[prep] {_i + 1}/{_n} samples encoded "
                      f"({_rate:.2f}/s, elapsed {_el:.0f}s, eta {_eta:.0f}s)", flush=True)
        self._save_cache()

    def _cache_signature(self):
        # Identifies the exact dataset the cache was built from. Includes caption
        # contents (not just paths) so editing a caption forces a rebuild, and an
        # image size/mtime proxy so replacing an image does too.
        import hashlib
        sig_pairs = []
        for img_path, cap_path in self.pairs:
            try:
                cap_hash = hashlib.sha256(
                    open(cap_path, "rb").read()).hexdigest()[:16]
            except Exception:
                cap_hash = "na"
            try:
                st = os.stat(img_path)
                img_key = f"{st.st_size}:{int(st.st_mtime)}"
            except Exception:
                img_key = "na"
            sig_pairs.append([os.path.basename(img_path), cap_hash, img_key])
        return {
            "pairs": sig_pairs,
            "size": self.size,
            "repeats": self.repeats,
            "shuffle_tags": self.shuffle_tags,
        }

    def _try_load_cache(self) -> bool:
        try:
            if not os.path.exists(self.cache_file):
                return False
            blob = torch.load(self.cache_file, map_location="cpu", weights_only=False)
            if blob.get("signature") != self._cache_signature():
                print(f"[prep] cache signature mismatch -- rebuilding", flush=True)
                return False
            self.cache = blob["cache"]
            print(f"[prep] LOADED latent cache ({len(self.cache)} samples) from "
                  f"{os.path.basename(self.cache_file)} -- skipping re-encode", flush=True)
            return True
        except Exception as exc:
            print(f"[prep] cache load failed ({exc}) -- rebuilding", flush=True)
            return False

    def _save_cache(self) -> None:
        try:
            blob = {"signature": self._cache_signature(), "cache": self.cache}
            tmp = self.cache_file + ".tmp"
            torch.save(blob, tmp)
            os.replace(tmp, self.cache_file)
            print(f"[prep] SAVED latent cache ({len(self.cache)} samples) to "
                  f"{os.path.basename(self.cache_file)}", flush=True)
        except Exception as exc:
            print(f"[prep] WARNING could not save cache: {exc}", flush=True)

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        c = self.cache[idx]
        return {"latents": c["latents"], "hidden": c["hidden"], "pooled": c["pooled"]}


def collate_fn(items):
    return {
        "latents": torch.stack([i["latents"] for i in items]),
        "hidden": torch.stack([i["hidden"] for i in items]),
        "pooled": torch.stack([i["pooled"] for i in items]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pretrained_model", default="models/sdxl-base")
    ap.add_argument("--train_data_dir", required=True)
    ap.add_argument("--output_dir", default="loras/realistic_posts")
    ap.add_argument("--resolution", type=int, default=1024)
    ap.add_argument("--train_batch_size", type=int, default=1)
    ap.add_argument("--num_train_epochs", type=int, default=10)
    ap.add_argument("--max_train_steps", type=int, default=0)
    ap.add_argument("--learning_rate", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--gradient_accumulation_steps", type=int, default=4)
    ap.add_argument("--mixed_precision", default="bf16", choices=["bf16", "fp16", "no"])
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--shuffle_tags", action="store_true")
    # --- Resume / checkpointing / manifest (Option B) ---
    ap.add_argument("--resume_from_checkpoint", type=str, default=None,
                    help="Path to a checkpoint dir, or 'latest' to auto-pick the "
                         "highest-step checkpoint in --output_dir.")
    ap.add_argument("--checkpointing_steps", type=int, default=200,
                    help="Save a full Accelerate state checkpoint every N global steps "
                         "(0 disables step-based checkpointing).")
    ap.add_argument("--checkpointing_epochs", type=int, default=1,
                    help="Save a checkpoint at the end of every N epochs "
                         "(0 disables epoch-based checkpointing).")
    ap.add_argument("--manifest", type=str, default=None,
                    help="Progress manifest JSON path "
                         "(default: <output_dir>/training_manifest.json).")
    args = ap.parse_args()

    if args.manifest is None:
        args.manifest = str(Path(args.output_dir) / "training_manifest.json")

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    # --- Initial manifest: announce intent, clear any stale error ---
    manifest = load_manifest(args.manifest)
    manifest.update({
        "recipe": "main-posts",
        "trainer": "train_xl_lora_folder.py",
        "output_dir": args.output_dir,
        "status": "starting",
        "stage": "training",
        "last_error": None,
        "updated_at": _now_iso(),
        "pid": os.getpid(),
    })
    write_manifest(args.manifest, manifest)

    accelerator = Accelerator(
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        mixed_precision=args.mixed_precision,
    )

    print(f"[loader] loading SDXL base from {args.pretrained_model}", flush=True)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        args.pretrained_model, torch_dtype=torch.float32,
        use_safetensors=True)
    tokenizer_one = pipe.tokenizer
    tokenizer_two = pipe.tokenizer_2
    # keep VAE + text encoders in fp32 to avoid fp16 overflow in latents/embeds
    text_encoder_one = pipe.text_encoder.to(accelerator.device)
    text_encoder_two = pipe.text_encoder_2.to(accelerator.device)
    vae = pipe.vae.to(accelerator.device)
    unet = pipe.unet.to(accelerator.device)
    del pipe

    # freeze everything, inject LoRA into unet (and optionally text encoders)
    unet.requires_grad_(False)
    unet.enable_gradient_checkpointing()
    lora_config = LoraConfig(
        r=args.rank, lora_alpha=args.rank, init_lora_weights="gaussian",
        target_modules=["to_k", "to_q", "to_v", "to_out.0"],
    )
    unet.add_adapter(lora_config)
    # force ALL unet params (incl. LoRA adapters + biases) to bf16 so conv
    # weight/bias dtypes stay consistent under accelerator autocast
    unet = unet.to(torch.bfloat16)
    trainable = [p for p in unet.parameters() if p.requires_grad]

    noise_scheduler = DDPMScheduler.from_config(
        "models/sdxl-base", subfolder="scheduler")

    dataset = FolderDataset(args.train_data_dir, tokenizer_one, tokenizer_two,
                            vae, text_encoder_one, text_encoder_two, accelerator.device,
                            size=args.resolution, repeats=args.repeats,
                            shuffle_tags=args.shuffle_tags)
    loader = DataLoader(dataset, batch_size=args.train_batch_size,
                        shuffle=True, collate_fn=collate_fn)

    optimizer = AdamW(trainable, lr=args.learning_rate, betas=(0.9, 0.999),
                      weight_decay=1e-4, eps=1e-8)

    unet, optimizer, loader = accelerator.prepare(unet, optimizer, loader)
    # Latents + text embeds are already precomputed and cached in FolderDataset, so
    # the VAE and both text encoders are dead weight for the training loop. Free
    # them off the GPU to give the UNet real VRAM headroom -- otherwise they pin
    # ~5-6 GiB and the allocator thrashes (observed: ~175 MiB free -> 70-130 s/step
    # at only 90W/320W, i.e. GPU starved). Freeing them restores GPU-bound steps.
    del vae, text_encoder_one, text_encoder_two
    import gc as _gc
    _gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # --- Resume setup (after prepare, so Accelerate can restore prepared state) ---
    starting_epoch = 0
    global_step = 0
    resumed_from = None
    if args.resume_from_checkpoint:
        if args.resume_from_checkpoint == "latest":
            ckpt = find_latest_checkpoint(args.output_dir)
        else:
            ckpt = Path(args.resume_from_checkpoint)
        if ckpt and ckpt.is_dir():
            try:
                accelerator.load_state(str(ckpt))
                # Restore loop counters from the checkpoint's own checkpoint_meta.json
                # (authoritative + survives a truncated manifest), falling back to the
                # manifest if needed.
                starting_epoch = 0
                global_step = 0
                meta_path = Path(ckpt) / "checkpoint_meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        starting_epoch = int(meta.get("completed_epochs", 0))
                        global_step = int(meta.get("global_step", 0))
                    except Exception:
                        pass
                if starting_epoch == 0 and global_step == 0:
                    m = load_manifest(args.manifest)
                    starting_epoch = int(m.get("completed_epochs", 0))
                    global_step = int(m.get("global_step", 0))
                resumed_from = str(ckpt)
                print(f"[resume] loaded state from {ckpt} "
                      f"(epoch={starting_epoch}, global_step={global_step})", flush=True)
                manifest.update({
                    "status": "training", "stage": "training",
                    "latest_checkpoint": str(ckpt),
                    "global_step": global_step, "completed_epochs": starting_epoch,
                    "resumed_from": resumed_from, "updated_at": _now_iso(),
                })
                write_manifest(args.manifest, manifest)
            except Exception as exc:
                print(f"[resume] WARNING could not load {ckpt}: {exc} "
                      f"-- starting a fresh run.", flush=True)
                manifest.update({"last_error": f"resume failed: {exc}", "updated_at": _now_iso()})
                write_manifest(args.manifest, manifest)
        else:
            print(f"[resume] checkpoint '{args.resume_from_checkpoint}' not found "
                  f"-- starting a fresh run.", flush=True)

    steps = global_step  # alias used in the loop logging
    max_steps = args.max_train_steps if args.max_train_steps > 0 else None
    print(f"[train] pairs={len(dataset)} batches={len(loader)} "
          f"epochs={args.num_train_epochs} lr={args.learning_rate} rank={args.rank} "
          f"starting_epoch={starting_epoch} global_step={global_step}", flush=True)

    os.makedirs(args.output_dir, exist_ok=True)

    def _save_checkpoint(epoch_done: int):
        """Save full Accelerate state + update manifest. epoch_done = completed epochs."""
        nonlocal global_step
        ckpt_dir = Path(args.output_dir) / f"checkpoint-{global_step:06d}"
        accelerator.save_state(str(ckpt_dir))
        # Authoritative resume state lives INSIDE the checkpoint dir (not the
        # manifest), so a truncated/killed manifest can never lose the step/epoch.
        ckpt_meta = {
            "global_step": global_step,
            "completed_epochs": epoch_done,
            "num_train_epochs": args.num_train_epochs,
            "saved_at": _now_iso(),
        }
        try:
            (Path(ckpt_dir) / "checkpoint_meta.json").write_text(
                json.dumps(ckpt_meta, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            print(f"[checkpoint] WARNING could not write checkpoint_meta: {exc}", flush=True)
        manifest.update({
            "status": "training",
            "stage": "training",
            "latest_checkpoint": str(ckpt_dir),
            "global_step": global_step,
            "completed_epochs": epoch_done,
            "updated_at": _now_iso(),
            "pid": os.getpid(),
        })
        write_manifest(args.manifest, manifest)
        print(f"[checkpoint] saved {ckpt_dir} (global_step={global_step}, "
              f"epochs_done={epoch_done})", flush=True)

    try:
        _train_t0 = _mono()
        for epoch in range(starting_epoch, args.num_train_epochs):
            unet.train()
            for batch in loader:
                with accelerator.accumulate(unet):
                    # Latents + text embeds are precomputed once in FolderDataset (cached
                    # on the GPU in fp32) — no per-step VAE/text-encoder cost.
                    latents = batch["latents"].to(accelerator.device, dtype=torch.float32)
                    hidden = batch["hidden"].to(accelerator.device)
                    pooled = batch["pooled"].to(accelerator.device)
                    bsz = latents.shape[0]
                    noise = torch.randn_like(latents)
                    timesteps = torch.randint(0, noise_scheduler.config.num_train_timesteps,
                                              (bsz,), device=latents.device).long()
                    noisy = noise_scheduler.add_noise(latents, noise, timesteps)
                    # SDXL needs time_ids (resolution + crop coords) in added_cond_kwargs
                    target_size = args.resolution
                    add_time_ids = torch.tensor(
                        [target_size, target_size, 0, 0, target_size, target_size],
                        dtype=torch.float32, device=hidden.device)
                    add_time_ids = add_time_ids.unsqueeze(0).repeat(bsz, 1)
                    # cast UNet inputs to the UNet's (bf16) dtype
                    udtype = next(unet.parameters()).dtype
                    model_pred = unet(
                        noisy.to(udtype), timesteps.to(udtype), hidden.to(udtype),
                        added_cond_kwargs={
                            "text_embeds": pooled.to(udtype),
                            "time_ids": add_time_ids.to(udtype)}).sample
                    if noise_scheduler.config.prediction_type == "v_prediction":
                        target = noise_scheduler.get_velocity(latents, noise, timesteps)
                    else:
                        target = noise
                    loss = torch.nn.functional.mse_loss(model_pred.float(), target.float())
                    accelerator.backward(loss)
                    # clip gradients to prevent explosion -> nan
                    accelerator.clip_grad_norm_(trainable, 1.0)
                    optimizer.step()
                    optimizer.zero_grad()
                global_step += 1
                steps = global_step
                if global_step % 10 == 0:
                    _el = _mono() - _train_t0
                    _rate = global_step / _el if _el > 0 else 0.0
                    print(f"[step {global_step}] loss={loss.item():.4f} "
                          f"({_rate:.3f} steps/s, {1/_rate:.1f}s/step)", flush=True)
                if args.checkpointing_steps and global_step % args.checkpointing_steps == 0:
                    _save_checkpoint(epoch)
                if max_steps and global_step >= max_steps:
                    break
            # end of epoch
            if args.checkpointing_epochs and (epoch + 1) % args.checkpointing_epochs == 0:
                _save_checkpoint(epoch + 1)
            if max_steps and global_step >= max_steps:
                break

        # save final LoRA
        unet = accelerator.unwrap_model(unet)
        final_path = Path(args.output_dir) / "pytorch_lora_weights.safetensors"
        unet.save_attn_procs(str(final_path))
        print(f"[done] saved LoRA -> {final_path}", flush=True)
        manifest.update({
            "status": "done",
            "stage": "complete",
            "completed_epochs": args.num_train_epochs,
            "global_step": global_step,
            "completed_at": _now_iso(),
            "updated_at": _now_iso(),
            "last_error": None,
            "pid": os.getpid(),
        })
        write_manifest(args.manifest, manifest)
    except KeyboardInterrupt:
        # Safe interruption: persist a checkpoint so the wrapper can resume.
        print("[interrupt] caught KeyboardInterrupt -- saving checkpoint before exit.", flush=True)
        try:
            _save_checkpoint(starting_epoch)
        except Exception as exc:
            print(f"[interrupt] checkpoint save failed: {exc}", flush=True)
        manifest.update({
            "status": "interrupted", "stage": "training",
            "global_step": global_step, "updated_at": _now_iso(),
            "last_error": "KeyboardInterrupt",
        })
        write_manifest(args.manifest, manifest)
        raise
    except Exception as exc:
        manifest.update({
            "status": "failed", "stage": "training",
            "global_step": global_step, "updated_at": _now_iso(),
            "last_error": f"{type(exc).__name__}: {exc}",
        })
        write_manifest(args.manifest, manifest)
        raise


if __name__ == "__main__":
    main()
