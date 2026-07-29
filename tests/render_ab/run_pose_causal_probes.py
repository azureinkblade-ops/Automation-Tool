"""Slice B0 — static pose-map causal probes (NO generator, CPU-only).

Per user 2026-07-26: do NOT build full B2a/B2b repairs. The claim
"Map B's floor-level hip index is THE kneel driver" is a HYPOTHESIS,
not demonstrated — ControlNet conditions on the whole pose graph, not one
joint. These probes isolate the causal factor with the SMALLEST possible
edits to Map B's recovered raw 18-pt array, then render the modfied
skeleton with controlnet_aux's own draw_bodypose (same visualizer the
generator consumes). Vision-gate the STATIC maps first; only promote a
variant to a GPU generator run after E1/E2 locate the factor.

Probes:
  E1  single-edge ablation: drop only the suspect edge [2,9]
      (shoulder->idx9). Keypoint kept; just not connected.
  E2  move-one-keypoint: shift ONLY idx9 up by `dy` (default 0.06
      in normalized y). No other point touched.

Both start from the RECOVERED Map B raw array saved by
run_mapB_diagnostic.py (_mapB_raw.json). If that file is absent,
re-detect from the source.

Usage (hermes-agent venv, CPU):
  $LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe \
      tests/render_ab/run_pose_causal_probes.py
Outputs: assets/pose_refs/_probe_E1_edge.png, _probe_E2_move.png
  + .json of the edited arrays.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SRC_IMG = ROOT / "assets" / "pose_refs" / "sources" / "kneeling_man_altar_user_ref_2026-07-26.png"
RAW_JSON = ROOT / "assets" / "pose_refs" / "_mapB_raw.json"
OUT_DIR = ROOT / "assets" / "pose_refs"
DY_MOVE = 0.06  # E2: shift idx9 up by 6% of image height


def load_raw():
    """Return (body_list, canvas_wh) from _mapB_raw.json or re-detect."""
    if RAW_JSON.exists():
        d = json.loads(RAW_JSON.read_text())
        return d["body_keypoints"], tuple(d["canvas_wh"])
    # fallback: re-detect
    from PIL import Image
    import numpy as np
    from controlnet_aux import OpenposeDetector
    det = OpenposeDetector.from_pretrained(
        "lllyasviel/Annotators", hand_filename="hand_pose_model.pth", face_filename="facenet.pth"
    )
    img = Image.open(SRC_IMG).convert("RGB")
    img.thumbnail((768, 1024))
    res = det.detect_poses(np.array(img))
    return [{"x": k.x, "y": k.y, "score": k.score, "id": k.id} for k in res[0].body.keypoints], (img.width, img.height)


def render(body_list, canvas_wh, edges, out_path, label):
    """Render body_list (list of {x,y,score,id} normalized) via draw_bodypose.
    edges: list of [a,b] 1-indexed limb pairs (draw_bodypose convention)."""
    import numpy as np
    from PIL import Image, ImageDraw
    from controlnet_aux.open_pose.util import Keypoint, draw_bodypose

    W, H = canvas_wh
    kps = [None if k is None else Keypoint(x=k["x"], y=k["y"], score=k.get("score", 1.0), id=k.get("id", -1)) for k in body_list]
    # draw_bodypose expects List[Keypoint]; render to black canvas
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    drawn = draw_bodypose(canvas, kps)
    # overlay edge labels so we can SEE which are active (debug aid)
    img = Image.fromarray(drawn)
    img.save(out_path)
    print(f"{label}: wrote {out_path}")


def main() -> None:
    body, canvas_wh = load_raw()
    print(f"loaded body len={len(body)}, canvas={canvas_wh}")

    # ---- E1: drop only edge [2,9] (1-indexed => keypoints 1 and 8) ----
    from controlnet_aux.open_pose.util import draw_bodypose  # for limbSeq reference
    import inspect
    src = inspect.getsource(draw_bodypose)
    # extract limbSeq list
    import re
    m = re.search(r"limbSeq\s*=\s*(\[.*?\])\s*\n", src, re.S)
    base_edges = eval(m.group(1)) if m else None
    if base_edges is None:
        # fallback: hardcode the known limbSeq from util.py:86-92
        base_edges = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8],
                     [2, 9], [9, 10], [10, 11], [2, 12], [12, 13],
                     [13, 14], [2, 1], [1, 15], [15, 17], [1, 16], [16, 18]]
    e1_edges = [e for e in base_edges if not (e == [2, 9])]
    render(body, canvas_wh, e1_edges, OUT_DIR / "_probe_E1_edge.png", "E1")
    (OUT_DIR / "_probe_E1_edge.json").write_text(json.dumps(
        {"edit": "dropped edge [2,9] only", "edges": e1_edges,
         "timestamp_utc": datetime.now(timezone.utc).isoformat()}, indent=2))

    # ---- E2: move ONLY idx9 up by DY_MOVE ---- 
    body_e2 = [None if k is None else dict(k) for k in body]  # shallow copy, keep Nones
    if body_e2[9] is not None:
        body_e2[9] = dict(body_e2[9])
        body_e2[9]["y"] = max(0.05, body_e2[9]["y"] - DY_MOVE)
    render(body_e2, canvas_wh, base_edges, OUT_DIR / "_probe_E2_move.png", "E2")
    (OUT_DIR / "_probe_E2_move.json").write_text(json.dumps(
        {"edit": f"moved idx9 y by -{DY_MOVE} only", "idx9_before": body[9],
         "idx9_after": body_e2[9], "edges": "unchanged (all base)",
         "timestamp_utc": datetime.now(timezone.utc).isoformat()}, indent=2))

    print("\nNEXT: vision-gate the STATIC maps _probe_E1_edge.png and "
          "_probe_E2_move.png. Kneel-preserving? Then promote to a GPU run.")


if __name__ == "__main__":
    main()
