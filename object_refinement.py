"""Stage 2 localized object-refinement contract.

CPU-only orchestration. GPU/model implementations are injected as backends so
this module remains testable and does not import torch or diffusers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class RefinementRequest:
    object_type: str
    target_region: str
    prompt: str
    mask_path: Path
    guide_path: Optional[Path] = None


@dataclass(frozen=True)
class BackendReceipt:
    model: str
    seed: int
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class AcceptanceVerdict:
    accepted: bool
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class RefinementResult:
    status: str
    output_path: Path
    candidate_path: Optional[Path] = None
    provenance_path: Optional[Path] = None
    diff_path: Optional[Path] = None
    verdict: Optional[AcceptanceVerdict] = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalize_review(
    pending_provenance_path: Path,
    verdict: AcceptanceVerdict,
) -> RefinementResult:
    """Finalize a quarantined candidate without rerunning the model.

    The pending record remains immutable. Source and candidate hashes are
    rechecked before an acceptance verdict can promote the candidate.
    """
    pending_provenance_path = Path(pending_provenance_path)
    payload = json.loads(pending_provenance_path.read_text(encoding="utf-8"))
    if payload.get("status") != "pending_review":
        raise ValueError("only pending_review provenance can be finalized")

    source_path = Path(payload["source_path"])
    candidate_path = Path(payload["candidate_path"])
    if _sha256(source_path) != payload.get("source_sha256"):
        raise RuntimeError("source changed after candidate generation")
    if _sha256(candidate_path) != payload.get("candidate_sha256"):
        raise RuntimeError("candidate changed after candidate generation")
    if int(payload.get("outside_mask_changed_pixels", -1)) != 0:
        verdict = AcceptanceVerdict(
            accepted=False,
            reasons=("outside-mask preservation gate failed",),
        )

    status = "accepted" if verdict.accepted else "rejected"
    output_path = candidate_path if verdict.accepted else source_path
    final_payload = dict(payload)
    final_payload.update(
        {
            "status": status,
            "acceptance": asdict(verdict),
            "output_path": str(output_path),
            "failure_returns_original": not verdict.accepted,
            "finalized_from": str(pending_provenance_path),
        }
    )
    final_path = pending_provenance_path.with_name("final-provenance.json")
    final_path.write_text(json.dumps(final_payload, indent=2), encoding="utf-8")
    return RefinementResult(
        status=status,
        output_path=output_path,
        candidate_path=candidate_path,
        provenance_path=final_path,
        diff_path=Path(payload["diff_path"]),
        verdict=verdict,
    )


class ObjectRefinementService:
    def __init__(
        self,
        backend: Callable[..., BackendReceipt],
        reviewer: Optional[Callable[..., AcceptanceVerdict]] = None,
    ):
        self.backend = backend
        self.reviewer = reviewer

    def refine(
        self,
        source_path: Path,
        request: RefinementRequest,
        work_dir: Path,
    ) -> RefinementResult:
        source_path = Path(source_path)
        enabled = os.getenv("VISUAL_OBJECT_REFINEMENT_ENABLED", "0").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return RefinementResult(status="disabled", output_path=source_path)

        # PIL is lazy-imported to preserve this module's CPU-only import boundary.
        from PIL import Image, ImageChops

        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        source = Image.open(source_path).convert("RGB")
        mask = Image.open(request.mask_path).convert("L")
        if source.size != mask.size:
            raise ValueError("source and mask dimensions must match")
        if mask.getbbox() is None:
            return RefinementResult(
                status="rejected",
                output_path=source_path,
                verdict=AcceptanceVerdict(
                    accepted=False,
                    reasons=("mask has no authorized pixels",),
                ),
            )

        candidate_path = work_dir / "candidate.png"
        diff_path = work_dir / "diff.png"
        provenance_path = work_dir / "provenance.json"

        receipt = self.backend(source_path, request, candidate_path)
        if not candidate_path.exists():
            raise RuntimeError("refinement backend did not create candidate image")

        source = Image.open(source_path).convert("RGB")
        candidate = Image.open(candidate_path).convert("RGB")
        mask = Image.open(request.mask_path).convert("L")
        if source.size != candidate.size or source.size != mask.size:
            raise ValueError("source, candidate, and mask dimensions must match")

        diff = ImageChops.difference(source, candidate)
        diff.save(diff_path)
        source_pixels = source.load()
        candidate_pixels = candidate.load()
        mask_pixels = mask.load()
        outside_changed = 0
        outside_max_delta = 0
        for y in range(source.height):
            for x in range(source.width):
                if mask_pixels[x, y] == 0:
                    deltas = tuple(
                        abs(source_pixels[x, y][i] - candidate_pixels[x, y][i])
                        for i in range(3)
                    )
                    if any(deltas):
                        outside_changed += 1
                        outside_max_delta = max(outside_max_delta, *deltas)

        if self.reviewer is None:
            verdict = AcceptanceVerdict(
                accepted=False,
                reasons=("candidate requires explicit review",),
            )
            status = "pending_review" if outside_changed == 0 else "rejected"
        else:
            verdict = self.reviewer(source_path, candidate_path, request)
            status = "accepted" if verdict.accepted and outside_changed == 0 else "rejected"
        output_path = candidate_path if status == "accepted" else source_path
        provenance = {
            "schema_version": 1,
            "status": status,
            "source_path": str(source_path),
            "source_sha256": _sha256(source_path),
            "mask_path": str(request.mask_path),
            "mask_sha256": _sha256(request.mask_path),
            "guide_path": str(request.guide_path) if request.guide_path else None,
            "guide_sha256": _sha256(request.guide_path) if request.guide_path else None,
            "candidate_path": str(candidate_path),
            "candidate_sha256": _sha256(candidate_path),
            "diff_path": str(diff_path),
            "object_type": request.object_type,
            "target_region": request.target_region,
            "prompt": request.prompt,
            "backend": asdict(receipt),
            "acceptance": asdict(verdict),
            "outside_mask_changed_pixels": outside_changed,
            "outside_mask_max_channel_delta": outside_max_delta,
            "output_path": str(output_path),
            "failure_returns_original": status != "accepted",
        }
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        return RefinementResult(
            status=status,
            output_path=output_path,
            candidate_path=candidate_path,
            provenance_path=provenance_path,
            diff_path=diff_path,
            verdict=verdict,
        )
