"""Rendered A/B harness for the Visual Director evidence gate.

PURPOSE
This is the configured control experiment that decides whether the Visual
Director integration should advance beyond PROMPT generation to actually
improving ASSETS. It is NOT Slice 2, NOT an AIVSB change, NOT a provider
change, NOT a Diffusers install, NOT reference-image/LoRA/IP-Adapter/ControlNet
work, and it does NOT touch production metadata, approved image banks, or
active TikTok packs.

CONTROL (single variable = the prompt)
  same scene, same provider, same model, same dimensions, same quality
  settings, same generation count. The ONLY difference between the two runs is
  which prompt set (legacy generic vs Visual Director canon-locked) is fed to
  the generator.

WHAT THIS MODULE DOES
  - capture_prompts(): pull the exact 3 legacy + 3 Director prompts for a scene
    via the real app.make_chapter_image_prompts() (env-gated), so the prompts
    are the ACTUAL production strings, not a reconstruction.
  - run_ab(): render 6 images (3 legacy + 3 director) through a pluggable
    RenderBackend. A MockBackend (no network, no cost) drives the committed
    tests; a RecordedBackend plays back real RenderResult traces we supply from
    the actual external-provider call (so the real traces flow through the same
    code path without embedding provider credentials in the repo).
  - RUBRIC + score_set() + evaluate_gate(): the side-by-side 1-5 scoring and the
    continue/stop gate from the directive.
  - write_manifest()/write_report(): machine + human artifacts.

WHAT THIS MODULE DOES NOT DO
  - It does not call the external provider itself. Generation is performed by
    the operator (Hermes image tool / FAL) and the returned provider+model trace
    is fed into RecordedBackend. This keeps paid-credit calls and credentials out
    of the repo and behind explicit authorization.

COST NOTE
  Generating real images through an external provider may consume paid credits.
  Building/capturing (MockBackend) is free. The operator must authorize the
  real generation step explicitly before any cost-bearing call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Dict, Any


# --------------------------------------------------------------------------
# Render backend abstraction
# --------------------------------------------------------------------------
@dataclass
class RenderResult:
    """One generation call's observable outcome. Provider trace is REAL data
    from the generation call, not the configured route label."""

    provider: str          # actual provider that rendered (e.g. 'FAL FLUX 2')
    model: str             # actual model string returned ('' if not exposed)
    path: str              # output file path (relative or absolute)
    ok: bool               # did the image generate
    error: str = ""        # failure reason if not ok
    cached: bool = False   # was this a reused/cached asset (must be False for A/B)
    text_in_image: bool = False   # did the engine render text inside the image
    duplicate_of: str = ""        # filename this duplicates (empty if unique)
    prompt: str = ""       # the exact prompt used
    trace_meta: Dict[str, Any] = field(default_factory=dict)


class RenderBackend(Protocol):
    def render(self, prompt: str, out_path: Path) -> RenderResult:
        ...


@dataclass
class MockBackend:
    """Deterministic, offline, free. Writes a 1x1 PNG so run_ab produces real
    files for tests. No provider call, no cost, no network."""

    provider: str = "mock-local"
    model: str = "mock-model"

    def render(self, prompt: str, out_path: Path) -> RenderResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # minimal valid 1x1 PNG (stdlib only)
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
            b"\xc0\xf0\x1f\x00\x05\x05\x02\x00\x9d\xc5\xd8\x1f\x00\x00\x00\x00IEND"
            b"\xaeB`\x82"
        )
        out_path.write_bytes(png)
        return RenderResult(
            provider=self.provider, model=self.model,
            path=str(out_path), ok=True, cached=False,
            text_in_image=False, duplicate_of="", prompt=prompt,
        )


@dataclass
class OpenAIAppBackend:
    """Drives the REAL application image workflow (app.create_openai_image ->
    OpenAI gpt-image-1). This is the faithful A/B path: same code the posts/videos
    use. Single variable = the prompt; provider/model/size/quality are fixed by
    the app's own defaults. Writes each image to the sandbox output dir and
    records the REAL provider trace (model/size/quality) via the app's own
    write_image_provider_trace, so we verify the engine that actually rendered
    rather than trusting a configured label.

    COST: each render is a billed OpenAI image call. Only use with explicit
    cost authorization. Requires ENABLE_EXTERNAL_AI=1 and OPENAI_API_KEY in env.
    """

    app_module: Any
    size: str = "1024x1536"
    quality: str = "medium"

    def render(self, prompt: str, out_path: Path) -> RenderResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime as _dt
        started = _dt.now(timezone.utc).isoformat()
        model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
        try:
            self.app_module.create_openai_image(prompt, out_path, size=self.size, quality=self.quality)
            ok = out_path.exists() and out_path.stat().st_size > 0
            error = "" if ok else "file not written"
        except Exception as exc:  # expose, never hide
            ok = False
            error = f"{type(exc).__name__}: {exc}"
        # Real provider trace (the engine that actually rendered, not the label).
        trace = {
            "provider": "openai",
            "model": model,
            "size": self.size,
            "quality": self.quality,
            "startedAt": started,
            "promptUsed": prompt,
        }
        try:
            self.app_module.write_image_provider_trace(out_path, trace)
        except Exception:
            pass
        return RenderResult(
            provider="openai", model=model, path=str(out_path), ok=ok, error=error,
            cached=False, text_in_image=False, duplicate_of="", prompt=prompt,
            trace_meta=trace,
        )
@dataclass
class RecordedBackend:
    """Plays back real RenderResult traces supplied by the operator (from the
    actual external-provider generation). Keeps credentials and the generation
    call itself out of this repo. Used for the real A/B run."""

    results: List[RenderResult]
    _i: int = 0

    def render(self, prompt: str, out_path: Path) -> RenderResult:
        # Recorded results already carry their own path; we copy the file into
        # the harness output dir so outputs live in legacy/ and visual-director/.
        res = self.results[self._i]
        self._i += 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        src = Path(res.path)
        if src.exists():
            out_path.write_bytes(src.read_bytes())
        return RenderResult(
            provider=res.provider, model=res.model, path=str(out_path),
            ok=res.ok, error=res.error, cached=res.cached,
            text_in_image=res.text_in_image, duplicate_of=res.duplicate_of,
            prompt=prompt, trace_meta=res.trace_meta,
        )


# --------------------------------------------------------------------------
# Prompt capture (real production strings)
# --------------------------------------------------------------------------
def capture_prompts(title: str, chapter: str, phrases: List[str], novel: str,
                    app_module) -> Dict[str, List[str]]:
    """Return {'legacy': [...3], 'director': [...3]} using the real
    make_chapter_image_prompts. Legacy = VISUAL_DIRECTOR off + AIVSB off (so the
    baseline is the true generic legacy string). Director = VISUAL_DIRECTOR on.
    Restores env afterwards."""
    prev_vd = os.environ.get("VISUAL_DIRECTOR_ENABLED")
    prev_aivsb = os.environ.get("AIVSB_REASONING_ENABLED")
    try:
        os.environ.pop("VISUAL_DIRECTOR_ENABLED", None)
        os.environ["AIVSB_REASONING_ENABLED"] = "off"
        legacy = app_module.make_chapter_image_prompts(title, chapter, phrases, novel)
        os.environ["VISUAL_DIRECTOR_ENABLED"] = "true"
        director = app_module.make_chapter_image_prompts(title, chapter, phrases, novel)
    finally:
        if prev_vd is None:
            os.environ.pop("VISUAL_DIRECTOR_ENABLED", None)
        else:
            os.environ["VISUAL_DIRECTOR_ENABLED"] = prev_vd
        if prev_aivsb is None:
            os.environ.pop("AIVSB_REASONING_ENABLED", None)
        else:
            os.environ["AIVSB_REASONING_ENABLED"] = prev_aivsb
    return {"legacy": list(legacy[:3]), "director": list(director[:3])}


# --------------------------------------------------------------------------
# A/B run
# --------------------------------------------------------------------------
def run_ab(scene_id: str, legacy_prompts: List[str], director_prompts: List[str],
           backend: RenderBackend, out_root: Path) -> Dict[str, Any]:
    """Generate 6 images (3 legacy + 3 director) via backend. Returns a structured
    result with per-image RenderResult data. Never reuses cached assets
    (backend is responsible for cached=False)."""
    out_root = Path(out_root)
    legacy_dir = out_root / "legacy"
    director_dir = out_root / "visual-director"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    director_dir.mkdir(parents=True, exist_ok=True)

    legacy_results = []
    for i, p in enumerate(legacy_prompts):
        r = backend.render(p, legacy_dir / f"legacy_{i}.png")
        legacy_results.append(asdict(r))
    director_results = []
    for i, p in enumerate(director_prompts):
        r = backend.render(p, director_dir / f"director_{i}.png")
        director_results.append(asdict(r))

    return {
        "scene_id": scene_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "legacy": legacy_results,
        "director": director_results,
    }


# --------------------------------------------------------------------------
# Scoring rubric + gate
# --------------------------------------------------------------------------
# 7 criteria from the directive. Each scored 1-5 for a three-image SET.
CRITERIA = [
    "character_identity",   # Liang looks like the same person across all 3
    "canon_accuracy",       # hair, robes, weapon, setting, cultivation correct
    "shot_differentiation", # establishing/character/action visibly distinct
    "sequence_coherence",   # images belong to one scene
    "mobile_readability",   # legible at phone-feed size
    "artifact_control",     # no severe anatomy/weapon/text/costume/composition fails
    "overall_improvement",  # Director set clearly more useful for the final short
]

# Per-image flags the judge must record (used by the gate + failure exposure).
PER_IMAGE_FLAGS = ["liang_recognizable", "text_in_image", "duplicate", "provider_refusal"]


@dataclass
class SetScore:
    criteria: Dict[str, int]               # 7 criteria, 1-5
    per_image: List[Dict[str, Any]]        # 3 entries, PER_IMAGE_FLAGS + notes


def evaluate_gate(legacy: SetScore, director: SetScore) -> Dict[str, Any]:
    """Apply the directive's continue/stop gate. A tie is NOT enough; a prettier
    isolated image is NOT enough. The Director must improve the USABLE SEQUENCE."""
    d = director.criteria
    l = legacy.criteria
    director_wins = d["overall_improvement"] > l["overall_improvement"]
    canon_no_regression = d["canon_accuracy"] >= l["canon_accuracy"]
    identity_count = sum(1 for img in director.per_image if img.get("liang_recognizable"))
    identity_ok = identity_count >= 2
    diff_ok = d["shot_differentiation"] >= 4  # visibly differentiated (3 distinct roles)

    recommend_continue = bool(director_wins and canon_no_regression and identity_ok and diff_ok)

    reasons = []
    reasons.append(f"overall_improvement Director {d['overall_improvement']} > Legacy {l['overall_improvement']}: {'PASS' if director_wins else 'FAIL (not a win)'}")
    reasons.append(f"canon_accuracy Director {d['canon_accuracy']} >= Legacy {l['canon_accuracy']}: {'PASS' if canon_no_regression else 'FAIL (regression)'}")
    reasons.append(f"Liang identity in >=2/3 Director images: {identity_count}/3 {'PASS' if identity_ok else 'FAIL'}")
    reasons.append(f"three-shot differentiation (>=4): Director {d['shot_differentiation']} {'PASS' if diff_ok else 'FAIL'}")

    return {
        "recommend_continue": recommend_continue,
        "director_wins": director_wins,
        "canon_no_regression": canon_no_regression,
        "liang_identity_count": identity_count,
        "shot_differentiation_ok": diff_ok,
        "reasons": reasons,
    }


# --------------------------------------------------------------------------
# Manifest + report writers
# --------------------------------------------------------------------------
def write_manifest(path: Path, data: Dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_report(path: Path, scene_id: str, prompts: Dict[str, List[str]],
                 ab: Dict[str, Any], legacy_score: SetScore, director_score: SetScore,
                 gate: Dict[str, Any]) -> None:
    """Side-by-side markdown review sheet for human scoring."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append(f"# Rendered A/B Review - {scene_id}")
    lines.append("")
    lines.append(f"Generated: {ab.get('generated_at','')}")
    lines.append("")
    lines.append("## Control (single variable = prompt)")
    lines.append("- same scene, same provider, same model, same dimensions, same quality, same count")
    lines.append("- legacy = `make_chapter_image_prompts` with VISUAL_DIRECTOR off")
    lines.append("- director = `make_chapter_image_prompts` with VISUAL_DIRECTOR on")
    lines.append("")
    lines.append("## Prompts (exact, as produced by the app)")
    for kind in ("legacy", "director"):
        lines.append(f"### {kind}")
        for i, pr in enumerate(prompts.get(kind, [])):
            lines.append(f"- [{i}] {pr}")
        lines.append("")
    lines.append("## Provider trace (actual, not the configured route label)")
    for kind in ("legacy", "director"):
        lines.append(f"### {kind}")
        for i, r in enumerate(ab.get(kind, [])):
            lines.append(f"- [{i}] file={Path(r.get('path','')).name} provider={r.get('provider')} model={r.get('model')} ok={r.get('ok')} cached={r.get('cached')} text_in_image={r.get('text_in_image')} duplicate_of={r.get('duplicate_of','')} error={r.get('error','')}")
        lines.append("")
    lines.append("## Scoring (1-5 per set)")
    lines.append("| Criterion | Legacy | Director |")
    lines.append("| --- | --- | --- |")
    for c in CRITERIA:
        lines.append(f"| {c} | {legacy_score.criteria.get(c,'')} | {director_score.criteria.get(c,'')} |")
    lines.append("")
    lines.append("## Per-image flags (Director)")
    lines.append("| # | Liang recognizable | text in image | duplicate | provider refusal |")
    lines.append("| --- | --- | --- | --- | --- |")
    for i, img in enumerate(director_score.per_image):
        lines.append(f"| {i} | {img.get('liang_recognizable')} | {img.get('text_in_image')} | {img.get('duplicate')} | {img.get('provider_refusal')} |")
    lines.append("")
    lines.append("## Gate")
    for reason in gate.get("reasons", []):
        lines.append(f"- {reason}")
    lines.append(f"- **RECOMMEND CONTINUE: {gate.get('recommend_continue')}**")
    lines.append("")
    lines.append("## Failures exposed (do not hide)")
    for kind in ("legacy", "director"):
        for i, r in enumerate(ab.get(kind, [])):
            if not r.get("ok"):
                lines.append(f"- [{kind} {i}] GENERATION ERROR: {r.get('error','')}")
            if r.get("cached"):
                lines.append(f"- [{kind} {i}] CACHED/REUSED ASSET (must be new)")
            if r.get("text_in_image"):
                lines.append(f"- [{kind} {i}] TEXT RENDERED INSIDE IMAGE")
            if r.get("duplicate_of"):
                lines.append(f"- [{kind} {i}] DUPLICATE of {r.get('duplicate_of')}")
    p.write_text("\n".join(lines), encoding="utf-8")


def build_score(criteria: Dict[str, int], per_image: List[Dict[str, Any]]) -> SetScore:
    return SetScore(criteria=criteria, per_image=per_image)
