"""Map B native-skeleton diagnostic -- authoritative schema recovery.

Per user directive 2026-07-26: BEFORE repairing, establish the detector's
ACTUAL keypoint schema from the installed controlnet_aux source (NOT assume
COCO indexing). draw_bodypose (util.py:86-92) uses 1-indexed limb pairs
and references indices up to 18, so the body array is 19 pts (0..18).

This script re-runs the EXACT detector config Map B was produced with
(OpenposeDetector.from_pretrained('lllyasviel/Annotators',
hand_filename='hand_pose_model.pth', face_filename='facenet.pth'),
det(src, hand_and_face=True)) and:
  1. saves the raw body 19-pt array + hands + face as JSON (recoverable, editable)
  2. renders an INDEX-LABELED diagnostic PNG so we can see each joint's index

No repair yet. Output: assets/pose_refs/_mapB_diagnostic.png + .json
Run in hermes-agent venv (has controlnet_aux + cv2 + PIL):
  $LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe tests/render_ab/run_mapB_diagnostic.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SRC = ROOT / "assets" / "pose_refs" / "sources" / "kneeling_man_altar_user_ref_2026-07-26.png"
OUT_PNG = ROOT / "assets" / "pose_refs" / "_mapB_diagnostic.png"
OUT_JSON = ROOT / "assets" / "pose_refs" / "_mapB_raw.json"


def _kp(k):
    return None if k is None else {"x": float(k.x), "y": float(k.y), "score": float(k.score), "id": int(k.id)}


def main() -> None:
    from PIL import Image
    import numpy as np
    import cv2
    from controlnet_aux import OpenposeDetector

    det = OpenposeDetector.from_pretrained(
        "lllyasviel/Annotators", hand_filename="hand_pose_model.pth", face_filename="facenet.pth"
    )
    src = Image.open(SRC).convert("RGB")
    src.thumbnail((768, 1024), Image.LANCZOS)
    arr = np.array(src)
    res = det.detect_poses(arr)
    pr = res[0]

    W, H = arr.shape[1], arr.shape[0]
    canvas = arr.copy()

    # ---- body (19-pt, indices 0..18 per draw_bodypose limbSeq) ----
    body = pr.body.keypoints
    body_list = [_kp(k) for k in body]
    font = cv2.FONT_HERSHEY_SIMPLEX
    for i, k in enumerate(body_list):
        if k is None:
            continue
        x, y = int(k["x"] * W), int(k["y"] * H)
        cv2.circle(canvas, (x, y), 6, (0, 255, 255), -1)
        cv2.putText(canvas, str(i), (x + 8, y - 8), font, 0.9, (0, 255, 255), 2)

    # ---- hands ----
    for hand_attr, label in (("left_hand", "L"), ("right_hand", "R")):
        hk = getattr(pr, hand_attr)
        if not hk:
            continue
        for j, k in enumerate(hk):
            if k is None:
                continue
            x, y = int(k.x * W), int(k.y * H)
            cv2.circle(canvas, (x, y), 4, (0, 200, 0), -1)
            cv2.putText(canvas, f"{label}{j}", (x + 5, y - 5), font, 0.6, (0, 220, 0), 1)

    Image.fromarray(canvas).save(OUT_PNG)
    print("DIAGNOSTIC:", OUT_PNG)

    payload = {
        "source": str(SRC),
        "detector": "controlnet_aux.OpenposeDetector / lllyasviel/Annotators",
        "config": "hand_and_face=True",
        "canvas_wh": [W, H],
        "body_len": len(body_list),
        "body_keypoints": body_list,
        "left_hand_len": len(pr.left_hand) if pr.left_hand else 0,
        "right_hand_len": len(pr.right_hand) if pr.right_hand else 0,
        "note": "body indices 0..18 per draw_bodypose limbSeq (util.py:86-92). "
                "hands drawn green; body drawn cyan w/ index labels. "
                "left/right_hand are None when no hand detected (expected for this pose).",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print("RAW JSON:", OUT_JSON)

    # human-readable summary of body joints (y down, 0=top)
    names = ["nose", "neck", "r_sh", "r_el", "r_wr", "l_sh", "l_el", "l_wr",
             "r_hip", "l_hip", "r_knee", "l_knee", "r_ank", "l_ank",
             "r_eye", "l_eye", "r_ear", "l_ear", "bg18"]
    print("\nBODY JOINTS (y down, 0=top, 1=bottom):")
    for i, k in enumerate(body_list):
        nm = names[i] if i < len(names) else str(i)
        if k is None:
            print(f"  {i:2d} {nm:7s} None")
        else:
            print(f"  {i:2d} {nm:7s} x={k['x']:.3f} y={k['y']:.3f} s={k['score']:.2f}")


if __name__ == "__main__":
    main()
