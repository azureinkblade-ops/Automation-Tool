"""Default wiring: MediaPipeline <- repo I2V production + presentation adapters.

Additive bridge only. ``MediaPipeline`` keeps its port protocols; this module
provides port implementations backed by:

* ``tools.i2v_production_adapter.ImageToVideoAdapter`` (backend routed per
  ``I2V_BACKEND`` via ``tools.i2v_backend_registry``; default ``svd_xt_1_1``;
  unknown ids fail closed inside the adapter), and
* ``tools.i2v_presentation_adapter.I2VPresentationAdapter.present_video``
  (takes a backend-neutral ``RawI2VClipRef``).

Signature bridge: ``PresentationPort.present_video(raw_path, sha, src_sha, *,
workflow_id)`` -> ``I2VPresentationAdapter.present_video(RawI2VClipRef, *,
workflow_id)``. Clip geometry (width/height/frames/fps) comes from the I2V
result recorded by the I2V port for the same video_sha256 (SVD defaults when
unknown).

No publishing, no identity canon writes, no GPU lease logic here.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from tools import i2v_backend_registry as reg
from tools import i2v_presentation_adapter as pa
from tools import i2v_production_adapter as i2v
from tools.media_pipeline_integration import (
    ApprovedStillRef,
    MediaPipeline,
    MediaRecordStore,
)

SettingsFactory = Callable[[str], i2v.I2VSettings]
MotionPlanFactory = Callable[[str, ApprovedStillRef], Optional[Mapping[str, Any]]]


def default_settings_for_backend(backend_id: str) -> i2v.I2VSettings:
    """SVD (default): adapter defaults, unchanged. Wan 2.2: native 720x1280."""
    if backend_id == reg.BACKEND_ID_WAN_22:
        return i2v.I2VSettings(
            target_width=i2v.WAN22_NATIVE_WIDTH,
            target_height=i2v.WAN22_NATIVE_HEIGHT,
            frame_count=i2v.WAN22_DEFAULT_LENGTH,
            fps=i2v.WAN22_DEFAULT_FPS,
        )
    return i2v.I2VSettings()


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class ProductionI2VPort:
    """``I2VPort`` backed by ``ImageToVideoAdapter``; backend from env per call."""

    adapter: Any  # ImageToVideoAdapter (or a fake with the same generate_video kwargs)
    environ: Optional[Mapping[str, str]] = None  # None -> os.environ at call time
    settings_factory: SettingsFactory = default_settings_for_backend
    motion_plan_factory: Optional[MotionPlanFactory] = None
    _results: Dict[str, Any] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def resolve_backend(self) -> str:
        env = self.environ if self.environ is not None else os.environ
        return reg.get_i2v_backend(env)

    def generate_video(self, still: ApprovedStillRef, *, seed: int, workflow_id: str) -> Any:
        backend_id = self.resolve_backend()
        image_bytes = None
        if still.image_path and Path(still.image_path).is_file():
            image_bytes = Path(still.image_path).read_bytes()
        source = i2v.SourceImageRef(
            source_image_sha256=still.source_image_sha256,
            image_generation_complete=True,
            image_validation_complete=True,
            image_source_approved=bool(still.image_source_approved),
            source_width=int(still.source_width),
            source_height=int(still.source_height),
            source_path=still.image_path or None,
            source_character_intent=still.source_character_intent,
            source_character_id_or_na=still.source_character_id_or_na,
            image_bytes=image_bytes,
        )
        motion_plan = self.motion_plan_factory(backend_id, still) if self.motion_plan_factory else None
        result = self.adapter.generate_video(
            source,
            motion_plan=motion_plan,
            backend_id=backend_id,
            seed=seed,
            settings=self.settings_factory(backend_id),
            workflow_id=workflow_id,
        )
        sha = _field(result, "video_sha256")
        if sha:
            with self._lock:
                self._results[str(sha)] = result
        return result

    def result_for(self, video_sha256: str) -> Any:
        with self._lock:
            return self._results.get(str(video_sha256))


def clip_ref_from_i2v_result(
    raw_video_path: str,
    video_sha256: str,
    source_image_sha256: str,
    i2v_result: Any = None,
) -> pa.RawI2VClipRef:
    """Build a backend-neutral clip ref; geometry from the I2V result when known."""
    kwargs: Dict[str, Any] = {}
    if i2v_result is not None:
        for src, dst in (("i2v_width", "width"), ("i2v_height", "height"),
                         ("frame_count", "frame_count"), ("fps", "fps")):
            v = _field(i2v_result, src)
            if v:
                kwargs[dst] = int(v)
    return pa.RawI2VClipRef(
        video_path=raw_video_path,
        video_sha256=video_sha256,
        source_image_sha256=source_image_sha256,
        **kwargs,
    )


@dataclass
class PresentationAdapterPort:
    """``PresentationPort`` bridging to ``I2VPresentationAdapter.present_video``."""

    adapter: Any  # I2VPresentationAdapter
    i2v_port: Optional[ProductionI2VPort] = None
    target_width: int = pa.DEFAULT_SOCIAL_WIDTH
    target_height: int = pa.DEFAULT_SOCIAL_HEIGHT

    def present_video(self, raw_video_path: str, video_sha256: str, source_image_sha256: str, *, workflow_id: str) -> Any:
        i2v_result = self.i2v_port.result_for(video_sha256) if self.i2v_port else None
        clip = clip_ref_from_i2v_result(raw_video_path, video_sha256, source_image_sha256, i2v_result)
        return self.adapter.present_video(
            clip,
            workflow_id=workflow_id,
            target_width=self.target_width,
            target_height=self.target_height,
        )


def build_default_media_pipeline(
    store_root: "os.PathLike[str] | str",
    *,
    transport: Any = None,
    gpu_metrics: Any = None,
    gpu_lease: Any = None,
    i2v_adapter: Any = None,
    presentation_adapter: Any = None,
    render: Optional[pa.RenderFn] = None,
    environ: Optional[Mapping[str, str]] = None,
    settings_factory: SettingsFactory = default_settings_for_backend,
    motion_plan_factory: Optional[MotionPlanFactory] = None,
    **pipeline_kwargs: Any,
) -> MediaPipeline:
    """Build a MediaPipeline wired to the repo's I2V + presentation adapters.

    Layout under ``store_root``: ``i2v_jobs/``, ``presentation_jobs/``,
    ``presented/``, ``media_records/``. Nothing runs at build time (no GPU,
    no network). Injected adapters override the defaults (tests / harness).
    """
    root = Path(store_root)
    if i2v_adapter is None:
        i2v_adapter = i2v.ImageToVideoAdapter(
            store=i2v.VideoJobStore(root / "i2v_jobs"),
            transport=transport,
            gpu_metrics=gpu_metrics,
            gpu_lease=gpu_lease,
        )
    if presentation_adapter is None:
        presentation_adapter = pa.I2VPresentationAdapter(
            store=pa.PresentationJobStore(root / "presentation_jobs"),
            render=render or pa.default_ffmpeg_render,
            output_dir=root / "presented",
        )
    i2v_port = ProductionI2VPort(
        adapter=i2v_adapter,
        environ=environ,
        settings_factory=settings_factory,
        motion_plan_factory=motion_plan_factory,
    )
    pres_port = PresentationAdapterPort(adapter=presentation_adapter, i2v_port=i2v_port)
    return MediaPipeline(
        store=MediaRecordStore(root / "media_records"),
        i2v=i2v_port,
        presentation=pres_port,
        **pipeline_kwargs,
    )


__all__ = [
    "ProductionI2VPort",
    "PresentationAdapterPort",
    "build_default_media_pipeline",
    "clip_ref_from_i2v_result",
    "default_settings_for_backend",
]
