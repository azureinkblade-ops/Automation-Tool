"""Slice B0 — R1 minimal anatomical repair (single-joint), separate asset.

Phase 2 of the user's optimization plan (2026-07-26). Map B is the FROZEN
baseline (NOT edited). R1 is a SEPARATE asset: reposition ONLY the invalid
hip joint (idx9) from its floor-level position to a plausible hip location,
preserving every other coordinate and every edge. This is the single
variable under test.

Per the user's plan: R1 must be validated with the IDENTICAL 4-seed
generator harness (run_map_compare.py --map R1). If kneeling survives AND
anatomy improves -> R1 becomes new baseline. If kneeling regresses ->
reject R1 immediately, keep Map B. No registry edit; Map B untouched.

This script only BUILDS the static R1 map (CPU, controlnet_aux draw_bodypose)
from Map B's recovered raw array (_mapB_raw.json). The generator run is a
separate step (run_map_compare.py).

R1 edit: idx9 (l_hip) from (x=0.359, y=0.855) -> (x=0.360, y=0.560).
  Rationale: mirrors idx8 (r_hip) y=0.543 but keeps idx9's own x. One
  coordinate pair changed. All 17 other joints + all edges untouched.
"""

from __future__ import annotations

import json
import sys
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RAW_JSON = ROOT / "assets" / "pose_refs" / "_mapB_raw.json"
OUT_PNG = ROOT / "assets" / "pose_refs" / "climax_kneel_detected_R1.png"
OUT_JSON = ROOT / "assets" / "pose_refs" / "climax_kneel_detected_R1.pose_meta.json"


def main() -> None:
    if not RAW_JSON.exists():
        raise SystemExit(f"missing {RAW_JSON} -- run run_mapB_diagnostic.py first")
    d = json.loads(RAW_JSON.read_text())
    body = d["body_keypoints"]
    canvas_wh = tuple(d["canvas_wh"])

    # import limbSeq from controlnet_aux util (same as diagnostic / generator)
    import re
    import inspect
    from controlnet_aux.open_pose.util import draw_bodypose
    src = inspect.getsource(draw_bodypose)
    m = re.search(r"limbSeq\s*=\s*(\[.*?\])\s*\n", src, re.S)
    edges = eval(m.group(1)) if m else [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8],
                                        [2, 9], [9, 10], [10, 11], [2, 12], [12, 13],
                                        [13, 14], [2, 1], [1, 15], [15, 17], [1, 16], [16, 18]]

    # ---- R1: move ONLY idx9 ----
    assert body[9] is not None, "idx9 was expected present"
    body_r1 = [None if k is None else dict(k) for k in body]
    before = dict(body_r1[9])
    body_r1[9] = dict(body_r1[9])
    body_r1[9]["x"] = 0.360
    body_r1[9]["y"] = 0.560
    after = dict(body_r1[9])

    # render via draw_bodypose
    import numpy as np
    from controlnet_aux.open_pose.util import Keypoint
    W, H = canvas_wh
    kps = [None if k is None else Keypoint(x=k["x"], y=k["y"], score=k.get("score", 1.0), id=k.get("id", -1)) for k in body_r1]
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    drawn = draw_bodypose(canvas, kps)
    from PIL import Image
    Image.fromarray(drawn).save(OUT_PNG)

    meta = {
        "asset": "climax_kneel_detected_R1.png",
        "derivation": "R1 minimal anatomical repair of Map B (climax_kneel_detected_B.png)",
        "variable_under_test": "single joint idx9 (l_hip) repositioned only",
        "idx9_before": before,
        "idx9_after": after,
        "other_joints_changed": "NONE (all 17 other coordinates preserved)",
        "edges_changed": "NONE (same limbSeq as Map B)",
        "source_raw": str(RAW_JSON),
        "canvas_wh": list(canvas_wh),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "next_step": "validate with run_map_compare.py --map R1 (identical 4-seed harness)",
    }
    OUT_JSON.write_text(json.dumps(meta, indent=2))
    print(f"R1 map: {OUT_PNG}")
    print(f"idx9 {before} -> {after}")
    print("All other joints + edges preserved. Generator validation is a SEPARATE step.")


if __name__ == "__main__":
    main()
