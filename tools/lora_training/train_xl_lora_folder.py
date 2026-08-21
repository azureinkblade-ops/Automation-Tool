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

SAFETY STOP (2026-08-19): the trainer supports a cooperative safety-stop file
(--safety_stop_file). When the watchdog writes STOP_REQUESTED, the trainer detects
it between batches, saves a full-state checkpoint, archives the request, and exits
cleanly via SystemExit(0). This is the primary safe-stop mechanism. taskkill / SIGTERM
do NOT reliably produce KeyboardInterrupt on Windows detached processes, so the
cooperative file is authoritative. See _check_safety_stop() and _archive_stop_request().
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
import math
import random
import re
import shutil
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, Future


def _mono() -> float:
    """Monotonic clock used for prep/training timing. Defined here because the
    prep and training loops call it; previously it was referenced but undefined,
    which crashed the trainer before prep could run."""
    return time.monotonic()
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _list_pairs(root):
    """List (image, caption) pairs in a dataset root (CPU/metadata only)."""
    pairs = []
    for p in sorted(glob.glob(os.path.join(root, "*"))):
        if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            cap = os.path.splitext(p)[0] + ".txt"
            if os.path.exists(cap):
                pairs.append((p, cap))
    return pairs


def _build_signature(pairs, size, repeats, shuffle_tags):
    """Dataset signature from metadata only (no model/GPU needed)."""
    import hashlib
    sig_pairs = []
    for img_path, cap_path in pairs:
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
        "size": size,
        "repeats": repeats,
        "shuffle_tags": shuffle_tags,
    }


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
        pairs = _list_pairs(root)
        # unique_pairs: the distinct source image/caption pairs. Expensive VAE +
        # text-encoder preprocessing is performed ONCE per unique pair and cached
        # -- never once per repeated training sample.
        self.unique_pairs = pairs
        # self.pairs: the training-order list (unique pairs repeated `repeats`
        # times) that drives __len__ and sampling frequency. Repeats affect how
        # often each cached latent is sampled, NOT how many times it is encoded.
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
        _n = len(self.unique_pairs)
        _diag = os.environ.get("LORA_PREP_DIAG") == "1"
        _hb = _mono()
        for _i, (img_path, cap_path) in enumerate(self.unique_pairs):
            if _diag:
                print(f"[prep] SAMPLE {_i + 1}/{_n} name={os.path.basename(img_path)} "
                      f"stage=start", flush=True)
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
            if _diag:
                print(f"[prep] SAMPLE {_i + 1}/{_n} name={os.path.basename(img_path)} "
                      f"stage=vae_encode", flush=True)
            with torch.no_grad():
                latent = self.vae.encode(
                    pixel.unsqueeze(0).to(self.device, dtype=torch.float32)
                ).latent_dist.sample().to(torch.float32) * 0.18215
                if _diag:
                    print(f"[prep] SAMPLE {_i + 1}/{_n} name={os.path.basename(img_path)} "
                          f"stage=text_encoders", flush=True)
                enc1 = self.text_encoder_one(ids1.unsqueeze(0).to(self.device), output_hidden_states=True)
                enc2 = self.text_encoder_two(ids2.unsqueeze(0).to(self.device), output_hidden_states=True)
                pooled = enc2[0]
                hidden = torch.cat([enc1.hidden_states[-2], enc2.hidden_states[-2]], dim=-1)
            self.cache.append({
                "latents": latent.squeeze(0).cpu(),
                "hidden": hidden.squeeze(0).cpu(),
                "pooled": pooled.squeeze(0).cpu(),
            })
            if _diag:
                _now = _mono()
                if _now - _hb >= 10.0:
                    _hb = _now
                    print(f"[prep] HEARTBEAT sample {_i + 1}/{_n} name={os.path.basename(img_path)} "
                          f"elapsed={_now - _t0:.0f}s", flush=True)
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
        return _build_signature(self.unique_pairs, self.size, self.repeats,
                                self.shuffle_tags)

    @staticmethod
    def is_cache_valid(root, size=1024, repeats=1, shuffle_tags=False,
                       cache_file=None):
        """CPU/metadata-only check: does a valid latent cache already exist for
        this dataset/config? Used to decide GPU placement of preprocessing-only
        components (VAE + text encoders) before they are loaded to CUDA."""
        if cache_file is None:
            cache_file = os.path.join(root, ".latent_cache.pt")
        pairs = _list_pairs(root)
        signature = _build_signature(pairs, size, repeats, shuffle_tags)
        try:
            if not os.path.exists(cache_file):
                return False
            blob = torch.load(cache_file, map_location="cpu", weights_only=False)
            if blob.get("signature") != signature:
                return False
            # Valid only if it covers every unique pair.
            return len(blob.get("cache", [])) == len(pairs)
        except Exception:
            return False

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
        # self.pairs has `repeats` copies of each unique pair; map the repeated
        # training index back to its single cached entry so repeated samples
        # reuse the same latent/text embeddings instead of duplicating them.
        c = self.cache[idx % len(self.unique_pairs)]
        return {"latents": c["latents"], "hidden": c["hidden"], "pooled": c["pooled"]}


def collate_fn(items):
    return {
        "latents": torch.stack([i["latents"] for i in items]),
        "hidden": torch.stack([i["hidden"] for i in items]),
        "pooled": torch.stack([i["pooled"] for i in items]),
    }


class SafetyStopRequested(Exception):
    """Raised by the training loop when a cooperative safety stop is requested.

    Carries the stop reason so the manifest/log can record it.
    """
    def __init__(self, reason: str = "UNKNOWN"):
        self.reason = reason
        super().__init__(f"safety stop requested: {reason}")


def _check_safety_stop(
    completed_epochs: int,
    current_epoch: int,
    next_batch_index: int,
    stop_file: Path,
    manifest: dict,
    manifest_path: Path,
    global_step: int,
    save_checkpoint_fn,
) -> None:
    """Check the cooperative safety-stop file between batches.

    If the file exists, read the reason, archive the file (don't just delete),
    save a full-state checkpoint, and raise SafetyStopRequested so the outer
    handler records the clean exit.

    The three loop-relative counters are passed in explicitly so their semantics
    are unambiguous (no global_step substitution).

    completed_epochs = number of FULLY completed epochs (audit only).
    current_epoch    = epoch currently being processed (0-indexed).
    next_batch_index = index of the batch that WOULD be processed next, if
                       training continued.  DataLoader position is NOT restored
                       on resume (RESUME_BATCH_SEMANTICS=EPOCH_RESTART); this
                       field is audit metadata only.
    """
    if not stop_file.exists():
        return
    # Read the stop request.  The watchdog writes structured JSON; parse it.
    raw = ""
    try:
        raw = stop_file.read_text(encoding="utf-8").strip()
    except Exception as exc:
        print(f"[safety] WARNING could not read stop file {stop_file}: {exc}", flush=True)
        return
    reason = "UNKNOWN"
    requested_run_id = ""
    requested_pid = 0
    try:
        payload = json.loads(raw)
        reason = payload.get("reason", "UNKNOWN")
        requested_run_id = payload.get("run_id", "")
        requested_pid = payload.get("trainer_root_pid", 0)
    except json.JSONDecodeError:
        # Legacy/plain-text fallback: first line is the reason
        try:
            reason = raw.splitlines()[0]
        except Exception:
            reason = "UNKNOWN"
    reason = reason.strip() or "UNKNOWN"

    # Verify the request belongs to the current run before honoring it.
    # This prevents a stale stop file from a previous run from immediately
    # terminating a new run (Gate 6 requirement).
    current_run_id = manifest.get("run_id", "")
    rejected = False
    if requested_run_id and current_run_id and requested_run_id != current_run_id:
        reason_reject = "STOP_REQUEST_REJECTED_RUN_ID_MISMATCH"
        print(f"[safety] {reason_reject}: file has '{requested_run_id}', "
              f"current run is '{current_run_id}'. Archiving as rejected.",
              flush=True)
        rejected = True
    elif requested_pid and current_run_id and requested_pid != manifest.get("pid", 0):
        reason_reject = "STOP_REQUEST_REJECTED_PID_MISMATCH"
        print(f"[safety] {reason_reject}: file has {requested_pid}, "
              f"current pid is {manifest.get('pid', 0)}. Archiving as rejected.",
              flush=True)
        rejected = True

    if rejected:
        _archive_rejected_stop_request(stop_file, reason_reject, requested_run_id,
                                       requested_pid, manifest, manifest_path)
        try:
            stop_file.unlink()
        except Exception:
            pass
        return

    # Archive the valid stop request instead of deleting, for auditability.
    try:
        _archive_stop_request(
            stop_file, reason, next_batch_index,
            completed_epochs, current_epoch, global_step, manifest, manifest_path,
        )
    except Exception as exc:
        print(f"[safety] WARNING could not archive stop file {stop_file}: {exc}", flush=True)
        try:
            stop_file.unlink()
        except Exception:
            pass
    print(f"[safety] STOP REQUESTED (reason={reason}) — saving checkpoint and exiting.",
          flush=True)
    # Save a full-state checkpoint at the CURRENT state (mid-epoch is fine).
    # completed_epochs = number of fully completed epochs (audit only).
    # current_epoch    = the epoch currently being processed (0-indexed); set here
    #   to reflect that the checkpoint was taken mid-epoch.
    # next_batch_index = the batch about to be processed next (audit only; DataLoader
    #   restarts at 0 on resume).
    _save_checkp = save_checkpoint_fn
    _save_checkp(
        completed_epochs,
        current_epoch=current_epoch,
        next_batch_in_epoch=next_batch_index,
    )
    manifest.update({
        "status": "safety_stopped",
        "stage": "training",
        "safety_stop_reason": reason,
        "global_step": global_step,
        "completed_epochs": completed_epochs,
        "current_epoch": current_epoch,
        "next_batch_index_within_epoch": next_batch_index,
        "updated_at": _now_iso(),
        "last_error": f"SAFETY_STOP:{reason}",
    })
    write_manifest(manifest_path, manifest)
    raise SafetyStopRequested(reason)


def _archive_rejected_stop_request(stop_file: Path, reject_reason: str,
                                    file_run_id: str, file_pid: int,
                                    manifest: dict,
                                    manifest_path: Path | None = None) -> None:
    """Archive a rejected (stale/mismatched) stop request for auditability."""
    if manifest_path is not None:
        archive_dir = Path(manifest_path).parent / "logs" / "safety_requests"
    else:
        archive_dir = Path(manifest.get("output_dir", ".")) / "logs" / "safety_requests"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = _now_iso()
    safe_ts = ts.replace(":", "-")
    archived_name = f"stop_request_REJECTED_{safe_ts}.json"
    archived = archive_dir / archived_name
    payload = {
        "reject_reason": reject_reason,
        "archived_at": ts,
        "original_reason": None,
        "requested_run_id": file_run_id,
        "requested_pid": file_pid,
        "current_pid": manifest.get("pid", 0),
        "current_run_id": manifest.get("run_id", "unknown"),
        "source_path": str(stop_file),
    }
    try:
        raw = stop_file.read_text(encoding="utf-8").strip()
        payload["original_reason"] = json.loads(raw).get("reason", None) if raw else None
    except Exception:
        pass
    tmp = archived.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(archived)


def _archive_stop_request(stop_file: Path, reason: str, batch_index: int,
                          completed_epochs: int, current_epoch: int,
                          global_step_val: int,
                          manifest: dict,
                          manifest_path: Path | None = None) -> None:
    """Move the stop-request file to the safety_requests archive with metadata."""
    if manifest_path is not None:
        archive_dir = Path(manifest_path).parent / "logs" / "safety_requests"
    else:
        archive_dir = Path(manifest.get("output_dir", ".")) / "logs" / "safety_requests"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = _now_iso()
    safe_ts = ts.replace(":", "-")
    archived_name = f"stop_request_{safe_ts}.json"
    archived = archive_dir / archived_name
    payload = {
        "reason": reason,
        "requested_at": ts,
        "run_id": manifest.get("run_id", "unknown"),
        "trainer_root_pid": manifest.get("pid", 0),
        "global_step": global_step_val,
        "completed_epochs": completed_epochs,
        "current_epoch": current_epoch,
        "next_batch_index_within_epoch": batch_index,
        "source_path": str(stop_file),
        "resulting_checkpoint_global_step": global_step_val,
    }
    tmp = archived.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(archived)
    # Remove the active stop file
    stop_file.unlink()


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
    ap.add_argument("--safety_stop_file", type=str, default=None,
                    help="Path to a cooperative safety-stop request file. "
                         "If this file exists at the start of a batch, the trainer "
                         "saves a full-state checkpoint and exits cleanly rather than "
                         "being force-killed. The file's first line is used as the "
                         "safety reason (e.g. GPU_MEMORY, GPU_THERMAL, WATCHDOG_FAILURE, "
                         "USER_REQUEST).")
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
    text_encoder_one = pipe.text_encoder
    text_encoder_two = pipe.text_encoder_2
    vae = pipe.vae
    unet = pipe.unet
    # Cache-aware device placement: when a valid latent cache already exists, the
    # VAE + both text encoders are NOT needed on GPU (their outputs are cached and
    # loaded CPU-side, then moved to the accelerator device per training step).
    # Placing them on GPU only on a cache MISS avoids the ~15.5 GiB startup
    # transient and lets the unchanged watchdog tolerate startup.
    cache_valid = FolderDataset.is_cache_valid(
        args.train_data_dir, args.resolution, args.repeats, args.shuffle_tags)
    if cache_valid:
        print("[loader] valid latent cache detected -- VAE/text encoders stay on "
              "CPU (cache-hit startup path)", flush=True)
        unet = unet.to(accelerator.device)
    else:
        print("[loader] no valid latent cache -- loading VAE/text encoders to GPU "
              "for preprocessing", flush=True)
        text_encoder_one = text_encoder_one.to(accelerator.device)
        text_encoder_two = text_encoder_two.to(accelerator.device)
        vae = vae.to(accelerator.device)
        unet = unet.to(accelerator.device)
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
                        # Audit: if current_epoch > completed_epochs, we're resuming
                        # mid-epoch.  DataLoader position is NOT restored by
                        # accelerator.load_state(), so we will restart the current
                        # epoch from batch 0.  This is the RESUME_BATCH_SEMANTICS.
                        current_ep = meta.get("current_epoch")
                        completed_ep = meta.get("completed_epochs")
                        if current_ep is not None and completed_ep is not None:
                            if current_ep > completed_ep:
                                print(f"[resume] WARNING: checkpoint was taken mid-epoch "
                                      f"(current_epoch={current_ep}, completed_epochs={completed_ep}). "
                                      f"Resuming will RESTART epoch {current_ep} from batch 0 — "
                                      f"some samples in that epoch will be re-seen.",
                                      flush=True)
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

    # Track the current batch index within the epoch for accurate interrupt
    # metadata.  global_step is a global counter and is NOT epoch-relative.
    current_batch_index = 0

    def _save_checkpoint(epoch_done: int, current_epoch: int | None = None, next_batch_in_epoch: int | None = None):
        """Save full Accelerate state + update manifest.

        epoch_done = number of FULLY completed epochs (for resume).
        current_epoch = the epoch currently being processed (0-indexed), if any.
        next_batch_in_epoch = index of the batch that WOULD be processed next
                              in current_epoch (audit info only; DataLoader position
                              is NOT restored on resume).
        """
        nonlocal global_step
        ckpt_dir = Path(args.output_dir) / f"checkpoint-{global_step:06d}"
        accelerator.save_state(str(ckpt_dir))
        # Authoritative resume state lives INSIDE the checkpoint dir (not the
        # manifest), so a truncated/killed manifest can never lose the step/epoch.
        ckpt_meta = {
            "global_step": global_step,
            "completed_epochs": epoch_done,
            "current_epoch": current_epoch if current_epoch is not None else epoch_done,
            "next_batch_index_within_epoch": next_batch_in_epoch if next_batch_in_epoch is not None else 0,
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
            "current_epoch": ckpt_meta["current_epoch"],
            "next_batch_index_within_epoch": ckpt_meta["next_batch_index_within_epoch"],
            "updated_at": _now_iso(),
            "pid": os.getpid(),
        })
        write_manifest(args.manifest, manifest)
        print(f"[checkpoint] saved {ckpt_dir} (global_step={global_step}, "
              f"completed_epochs={epoch_done}, current_epoch={ckpt_meta['current_epoch']}, "
              f"next_batch_in_epoch={ckpt_meta['next_batch_index_within_epoch']})", flush=True)

    # Loop-relative state for accurate checkpoint metadata.
    #   current_epoch_index  — epoch currently being processed (0-indexed), or
    #     the epoch that was interrupted.
    #   completed_epochs_count — number of FULLY completed epochs (incremented
    #     only after an epoch genuinely finishes).
    #   next_batch_index_within_epoch — index of the batch about to execute, or
    #     (after a batch completes) the index of the NEXT batch.  This is audit
    #     metadata only: DataLoader position is NOT restored on resume.
    #
    # Resume semantics: RESUME_BATCH_SEMANTICS=EPOCH_RESTART.
    #   accelerator.load_state() restores model + optimizer + scheduler + RNG +
    #   trainer global_step, but does NOT restore DataLoader iteration position.
    #   A mid-epoch checkpoint therefore restarts the interrupted epoch from batch 0.
    #   next_batch_index_within_epoch records where the DataLoader WOULD resume;
    #   it is NOT where it actually resumes.
    current_epoch_index = starting_epoch
    completed_epochs_count = starting_epoch
    next_batch_index_within_epoch = 0

    try:
        _train_t0 = _mono()
        for epoch in range(starting_epoch, args.num_train_epochs):
            current_epoch_index = epoch
            next_batch_index_within_epoch = 0
            # Per-epoch bookkeeping: assume the epoch completes naturally unless
            # an intentional early break (e.g. max_train_steps reached) sets this
            # False. Must be initialized before the batch loop so the post-loop
            # `if epoch_completed:` check never hits an unbound variable.
            epoch_completed = True

            unet.train()

            for batch_index, batch in enumerate(loader):
                # The next batch about to execute.
                next_batch_index_within_epoch = batch_index

                # Safety stop is checked BEFORE any work on this batch.
                if args.safety_stop_file:
                    _check_safety_stop(
                        completed_epochs_count,
                        current_epoch_index,
                        next_batch_index_within_epoch,
                        Path(args.safety_stop_file),
                        manifest,
                        Path(args.manifest),
                        global_step,
                        save_checkpoint_fn=_save_checkpoint,
                    )

                with accelerator.accumulate(unet):
                    # --- full batch body unchanged ---
                    latents = batch["latents"].to(accelerator.device, dtype=torch.float32)
                    hidden = batch["hidden"].to(accelerator.device)
                    pooled = batch["pooled"].to(accelerator.device)
                    bsz = latents.shape[0]
                    noise = torch.randn_like(latents)
                    timesteps = torch.randint(0, noise_scheduler.config.num_train_timesteps,
                                              (bsz,), device=latents.device).long()
                    noisy = noise_scheduler.add_noise(latents, noise, timesteps)
                    target_size = args.resolution
                    add_time_ids = torch.tensor(
                        [target_size, target_size, 0, 0, target_size, target_size],
                        dtype=torch.float32, device=hidden.device)
                    add_time_ids = add_time_ids.unsqueeze(0).repeat(bsz, 1)
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
                    accelerator.clip_grad_norm_(trainable, 1.0)
                    optimizer.step()
                    optimizer.zero_grad()

                # This batch is now fully reflected in model/optimizer state.
                global_step += 1
                steps = global_step

                # If checkpointed now, the NEXT batch would be batch_index + 1.
                next_batch_index_within_epoch = batch_index + 1

                if global_step % 10 == 0:
                    _el = _mono() - _train_t0
                    _rate = global_step / _el if _el > 0 else 0.0
                    print(f"[step {global_step}] loss={loss.item():.4f} "
                          f"({_rate:.3f} steps/s, {1/_rate:.1f}s/step)", flush=True)

                if (
                    args.checkpointing_steps
                    and global_step % args.checkpointing_steps == 0
                ):
                    _save_checkpoint(
                        completed_epochs_count,
                        current_epoch=current_epoch_index,
                        next_batch_in_epoch=next_batch_index_within_epoch,
                    )

                if max_steps and global_step >= max_steps:
                    epoch_completed = False
                    break

            # Genuine end-of-epoch checkpoint.
            if epoch_completed:
                completed_epochs_count = epoch + 1
                next_batch_index_within_epoch = 0

                if (
                    args.checkpointing_epochs
                    and completed_epochs_count % args.checkpointing_epochs == 0
                ):
                    _save_checkpoint(
                        completed_epochs_count,
                        current_epoch=None,
                        next_batch_in_epoch=0,
                    )

            if max_steps and global_step >= max_steps:
                break

        # save final LoRA
        # NOTE: use save_lora_adapter (not the legacy save_attn_procs) because
        # this script attaches LoRA via unet.add_adapter(LoraConfig). save_attn_procs
        # expects the old AttnProcs attach style and silently writes a 0-byte file.
        unet = accelerator.unwrap_model(unet)
        final_path = Path(args.output_dir) / "pytorch_lora_weights.safetensors"
        _tmp_dir = Path(args.output_dir) / ".final_adapter_tmp"
        _tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            unet.save_lora_adapter(
                save_directory=str(_tmp_dir),
                adapter_name="default",
                safe_serialization=True,
                weight_name="pytorch_lora_weights.safetensors",
            )
            _written = _tmp_dir / "pytorch_lora_weights.safetensors"
            if not _written.exists() or _written.stat().st_size == 0:
                raise RuntimeError("save_lora_adapter produced an empty weights file")
            # atomic-ish replace of the final path
            if final_path.exists():
                final_path.unlink()
            _written.replace(final_path)
        finally:
            shutil.rmtree(_tmp_dir, ignore_errors=True)
        if not final_path.exists() or final_path.stat().st_size == 0:
            raise RuntimeError("final LoRA weights missing or empty after save")
        print(f"[done] saved LoRA -> {final_path} ({final_path.stat().st_size} bytes)", flush=True)
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
            _save_checkpoint(
                completed_epochs_count,
                current_epoch=current_epoch_index,
                next_batch_in_epoch=next_batch_index_within_epoch,
            )
        except Exception as exc:
            print(f"[interrupt] checkpoint save failed: {exc}", flush=True)
        manifest.update({
            "status": "interrupted",
            "stage": "training",
            "global_step": global_step,
            "completed_epochs": completed_epochs_count,
            "current_epoch": current_epoch_index,
            "next_batch_index_within_epoch": next_batch_index_within_epoch,
            "resume_batch_semantics": "EPOCH_RESTART",
            "updated_at": _now_iso(),
        })
        write_manifest(args.manifest, manifest)
        raise
    except SafetyStopRequested:
        # Cooperative safety stop: already checkpointed + manifest updated inside
        # _check_safety_stop. Exit cleanly so the watchdog can confirm.
        print("[safety] cooperative safety stop acknowledged; exiting.", flush=True)
        raise SystemExit(0)
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
