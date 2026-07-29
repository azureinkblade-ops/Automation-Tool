"""Subprocess adapter for the local SDXL Stage 2 object refiner."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Optional

from object_refinement import BackendReceipt, RefinementRequest


@dataclass(frozen=True)
class LocalSDXLInpaintBackend:
    python_executable: str
    script_path: Path
    model_path: Path
    lora_path: Optional[Path] = None
    seed: int = 917364
    strength: float = 0.25
    steps: int = 35
    guidance_scale: float = 7.0
    lora_scale: float = 0.50
    negative_prompt: str = "duplicate object, floating object, malformed object, text, watermark"
    timeout_seconds: int = 600

    def __call__(
        self,
        source_path: Path,
        request: RefinementRequest,
        candidate_path: Path,
    ) -> BackendReceipt:
        candidate_path = Path(candidate_path)
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.python_executable,
            str(self.script_path),
            "--source", str(source_path),
            "--mask", str(request.mask_path),
            "--output", str(candidate_path),
            "--prompt", request.prompt,
            "--negative-prompt", self.negative_prompt,
            "--model", str(self.model_path),
            "--seed", str(self.seed),
            "--strength", str(self.strength),
            "--steps", str(self.steps),
            "--guidance-scale", str(self.guidance_scale),
        ]
        if request.guide_path is not None:
            command.extend(["--guide", str(request.guide_path)])
        if self.lora_path is not None:
            command.extend(
                ["--lora", str(self.lora_path), "--lora-scale", str(self.lora_scale)]
            )

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            raise RuntimeError(f"local object refiner failed ({completed.returncode}): {detail}")
        if not candidate_path.exists():
            raise RuntimeError("local object refiner reported success without an output image")

        sidecar = candidate_path.with_suffix(candidate_path.suffix + ".refinement.json")
        if not sidecar.exists():
            raise RuntimeError("local object refiner did not write provenance sidecar")
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        return BackendReceipt(
            model=str(payload["model"]),
            seed=int(payload["seed"]),
            parameters=dict(payload.get("parameters") or {}),
        )
