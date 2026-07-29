"""Create immutable Stage 2 V1 masks, guides, and executable manifest."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / ".hermes/evidence"


def load_index(name: str) -> dict[int, Path]:
    payload = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    return {int(row["index"]): Path(row["path"]) for row in payload["rows"]}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()


# index source, object class, normalized mask box, actual visible strata
SPECS = [
    ("v1-001", "campaign2", 5, "sheathed_sword", (0.52, 0.43, 0.66, 0.84), "EN", "interior", "warm_dim", "standing", "outer_hip"),
    ("v1-002", "campaign2", 10, "sheathed_sword", (0.52, 0.42, 0.79, 0.93), "EN", "exterior", "cool_dim", "standing", "outer_hip"),
    ("v1-003", "campaign2", 17, "sheathed_sword", (0.48, 0.45, 0.82, 0.93), "EN", "exterior", "cool_dim", "standing", "outer_hip"),
    ("v1-004", "campaign1", 48, "sheathed_sword", (0.53, 0.42, 0.78, 0.91), "EN", "exterior", "warm_bright", "standing", "outer_hip"),
    ("v1-005", "ha", 3, "sheathed_sword", (0.39, 0.40, 0.65, 0.91), "HA", "isolated_character", "cool_dim", "standing", "outer_hip"),
    ("v1-006", "hp", 3, "sheathed_sword", (0.44, 0.35, 0.65, 0.69), "HP", "interior", "cool_bright", "kneeling", "outer_hip"),
    ("v1-007", "campaign2", 1, "drawn_sword", (0.24, 0.48, 0.97, 0.92), "EN", "exterior", "cool_bright", "standing", "hand_to_blade"),
    ("v1-008", "campaign2", 7, "drawn_sword", (0.05, 0.53, 0.96, 0.80), "EN", "interior", "warm_dim", "close_medium", "hand_to_blade"),
    ("v1-009", "campaign2", 14, "drawn_sword", (0.10, 0.50, 0.62, 0.86), "EN", "interior", "warm_bright", "walking_action", "hand_to_blade"),
    ("v1-010", "campaign2", 16, "drawn_sword", (0.10, 0.50, 0.64, 0.90), "EN", "exterior", "warm_bright", "standing", "hand_to_blade"),
    ("v1-011", "campaign2", 12, "scabbard_weapon_repair", (0.25, 0.50, 0.56, 0.91), "EN", "exterior", "warm_dim", "standing", "hip_or_hand"),
    ("v1-012", "campaign2", 24, "scabbard_weapon_repair", (0.37, 0.06, 0.62, 0.94), "EN", "interior", "cool_dim", "close_medium", "hip_or_hand"),
    ("v1-013", "campaign1", 37, "scabbard_weapon_repair", (0.44, 0.50, 0.80, 0.95), "EN", "exterior", "warm_bright", "standing", "hip_or_hand"),
    ("v1-014", "hp", 2, "scabbard_weapon_repair", (0.43, 0.48, 0.89, 0.73), "HP", "exterior", "warm_bright", "walking_action", "hip_or_hand"),
    ("v1-015", "campaign2", 4, "non_weapon_prop", (0.44, 0.46, 0.59, 0.66), "EN", "interior", "warm_dim", "standing", "hand_or_near_body"),
    ("v1-016", "campaign2", 21, "non_weapon_prop", (0.57, 0.48, 0.79, 0.73), "EN", "exterior", "warm_bright", "standing", "hand_or_near_body"),
    ("v1-017", "campaign1", 43, "non_weapon_prop", (0.30, 0.52, 0.58, 0.82), "EN", "interior", "warm_bright", "standing", "hand_or_near_body"),
    ("v1-018", "hp", 1, "non_weapon_prop", (0.73, 0.75, 0.91, 0.94), "HP", "exterior", "cool_bright", "wide_environment", "hand_or_near_body"),
    ("v1-019", "campaign1", 12, "hand_repair", (0.55, 0.55, 0.72, 0.73), "EN", "exterior", "cool_dim", "close_medium", "hand"),
    ("v1-020", "campaign1", 47, "hand_repair", (0.27, 0.54, 0.47, 0.73), "EN", "exterior", "warm_bright", "close_medium", "hand"),
    ("v1-021", "ha", 2, "hand_repair", (0.30, 0.45, 0.49, 0.67), "HA", "isolated_character", "cool_dim", "walking_action", "hand"),
    ("v1-022", "campaign2", 26, "clothing_defect", (0.42, 0.54, 0.63, 0.92), "EN", "interior", "cool_bright", "standing", "garment_region"),
    ("v1-023", "campaign1", 39, "clothing_defect", (0.42, 0.35, 0.72, 0.85), "EN", "exterior", "cool_bright", "standing", "garment_region"),
    ("v1-024", "ha", 1, "clothing_defect", (0.28, 0.42, 0.75, 0.92), "HA", "isolated_character", "cool_dim", "close_medium", "garment_region"),
]

PROMPTS = {
    "sheathed_sword": "LOCAL REFINEMENT ONLY: one coherent standard-length Chinese jian in a rigid dark scabbard attached naturally at the outer hip, wrapped hilt and simple horizontal guard; preserve identity, pose, anatomy, clothing design, and composition",
    "drawn_sword": "LOCAL REFINEMENT ONLY: repair the selected weapon into one coherent drawn Chinese jian extending rigidly from the character's hand, straight silver double-edged blade, wrapped hilt and simple guard; preserve identity, pose, anatomy, clothing, and composition",
    "scabbard_weapon_repair": "LOCAL REFINEMENT ONLY: repair the selected weapon and scabbard geometry into one coherent physically attached Chinese jian assembly, rigid blade or scabbard, wrapped hilt and simple guard; preserve identity, pose, anatomy, clothing, and composition",
    "non_weapon_prop": "LOCAL REFINEMENT ONLY: add one coherent palm-sized glowing jade talisman lantern held or attached naturally near the character, clearly non-weapon; preserve identity, pose, anatomy, clothing, and composition",
    "hand_repair": "LOCAL REFINEMENT ONLY: repair only the selected hand into one anatomically plausible human hand with five natural fingers matching the existing pose and grip; preserve identity, pose, weapon, clothing, and composition",
    "clothing_defect": "LOCAL REFINEMENT ONLY: repair only the selected garment region with coherent seams, folds, closure, and fabric continuity matching the existing costume; preserve identity, pose, anatomy, weapon, and composition",
}


GUIDE_ENDPOINTS = {
    "v1-001": ((0.58, 0.49), (0.62, 0.82)),
    "v1-002": ((0.65, 0.50), (0.72, 0.88)),
    "v1-003": ((0.58, 0.50), (0.64, 0.89)),
    "v1-004": ((0.62, 0.48), (0.69, 0.88)),
    "v1-005": ((0.52, 0.48), (0.58, 0.85)),
    "v1-006": ((0.54, 0.41), (0.60, 0.67)),
    "v1-007": ((0.38, 0.60), (0.92, 0.82)),
    "v1-008": ((0.24, 0.66), (0.91, 0.70)),
    "v1-009": ((0.48, 0.59), (0.15, 0.82)),
    "v1-010": ((0.49, 0.60), (0.16, 0.86)),
    "v1-011": ((0.40, 0.56), (0.35, 0.87)),
    "v1-012": ((0.50, 0.10), (0.52, 0.90)),
    "v1-013": ((0.55, 0.58), (0.70, 0.90)),
    "v1-014": ((0.52, 0.56), (0.82, 0.67)),
}

PROP_CENTERS = {
    "v1-015": (0.52, 0.56),
    "v1-016": (0.68, 0.60),
    "v1-017": (0.40, 0.65),
    "v1-018": (0.81, 0.85),
}


def draw_guide(source, mask_box, object_class, case_id):
    from PIL import ImageDraw

    guide = source.copy()
    draw = ImageDraw.Draw(guide)
    x0, y0, x1, y1 = mask_box
    width = max(4, source.width // 80)
    if object_class in {"sheathed_sword", "scabbard_weapon_repair"}:
        raw_start, raw_end = GUIDE_ENDPOINTS[case_id]
        start = (int(raw_start[0] * source.width), int(raw_start[1] * source.height))
        end = (int(raw_end[0] * source.width), int(raw_end[1] * source.height))
        draw.line((start, end), fill=(25, 38, 45), width=width * 3)
        draw.line((start, end), fill=(96, 135, 145), width=width)
        draw.line((start[0] - width * 3, start[1] + width * 3, start[0] + width * 3, start[1] + width * 3), fill=(205, 215, 220), width=width)
    elif object_class == "drawn_sword":
        raw_start, raw_end = GUIDE_ENDPOINTS[case_id]
        start = (int(raw_start[0] * source.width), int(raw_start[1] * source.height))
        end = (int(raw_end[0] * source.width), int(raw_end[1] * source.height))
        draw.line((start, end), fill=(230, 238, 242), width=width * 2)
        draw.line((start, end), fill=(128, 150, 160), width=width)
        draw.line((start[0] - width * 2, start[1] - width * 2, start[0] + width * 3, start[1] + width * 3), fill=(210, 190, 130), width=width)
    elif object_class == "non_weapon_prop":
        raw_center = PROP_CENTERS[case_id]
        cx = int(raw_center[0] * source.width)
        cy = int(raw_center[1] * source.height)
        radius = max(width * 4, min(x1 - x0, y1 - y0) // 5)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(75, 210, 175), outline=(215, 255, 225), width=width)
        draw.line((cx, cy - radius * 2, cx, cy - radius), fill=(90, 70, 45), width=width)
    else:
        return None
    return guide


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--started-at", required=True)
    args = parser.parse_args()

    from PIL import Image, ImageChops, ImageDraw

    indexes = {
        "campaign1": load_index("stage2-v1-campaign-contact-sheet-1-index.json"),
        "campaign2": load_index("stage2-v1-campaign-contact-sheet-2-index.json"),
        "ha": load_index("stage2-v1-ha-generated-sheet-index.json"),
        "hp": load_index("stage2-v1-hp-track3-sheet-index.json"),
    }
    base = args.manifest.parent.resolve()
    cases = []
    prep_rows = []
    args.output_root.mkdir(parents=True, exist_ok=True)
    for case_id, index_name, image_index, object_class, normalized, novel, scene_type, lighting, composition, placement in SPECS:
        started = time.perf_counter()
        source_path = indexes[index_name][image_index].resolve()
        source = Image.open(source_path).convert("RGB")
        x0, y0, x1, y1 = (
            int(normalized[0] * source.width), int(normalized[1] * source.height),
            int(normalized[2] * source.width), int(normalized[3] * source.height),
        )
        case_dir = (args.output_root / case_id).resolve()
        case_dir.mkdir(parents=True, exist_ok=True)
        mask_path = case_dir / "mask.png"
        mask = Image.new("L", source.size, 0)
        draw = ImageDraw.Draw(mask)
        radius = max(6, min(source.size) // 60)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=255)
        mask.save(mask_path)
        guide = draw_guide(source, (x0, y0, x1, y1), object_class, case_id)
        guide_path = case_dir / "guide.png" if guide is not None else None
        if guide_path is not None:
            guide_delta = ImageChops.difference(source, guide)
            delta_pixels = guide_delta.load()
            mask_pixels = mask.load()
            outside_guide_pixels = sum(
                1
                for py in range(source.height)
                for px in range(source.width)
                if mask_pixels[px, py] == 0 and delta_pixels[px, py] != (0, 0, 0)
            )
            if outside_guide_pixels:
                raise ValueError(
                    f"{case_id}: guide changes {outside_guide_pixels} pixels outside mask"
                )
            guide.save(guide_path)
        preparation_seconds = time.perf_counter() - started
        prep_rows.append({"case_id": case_id, "automated_mask_guide_preparation_seconds": preparation_seconds})
        coverage = sum(1 for value in mask.getdata() if value > 0) / (source.width * source.height)
        cases.append({
            "case_id": case_id,
            "strata": {
                "object_class": object_class,
                "novel": novel,
                "scene_type": scene_type,
                "lighting": lighting,
                "composition": composition,
                "mask_size": "small" if coverage < 0.12 else "medium",
                "target_placement": placement,
            },
            "source_path": rel(source_path, base),
            "mask_path": rel(mask_path, base),
            "guide_path": rel(guide_path, base) if guide_path else None,
            "final_provenance_path": rel((ROOT / "tests/render_ab/output/stage2_v1" / case_id / "final-provenance.json"), base),
            "review_path": rel((EVIDENCE / "stage2-v1-reviews" / f"{case_id}.json"), base),
            "execution_record_path": rel(
                (EVIDENCE / "stage2-v1-execution" / f"{case_id}.json"), base
            ),
            "object_type": object_class,
            "target_region": placement,
            "prompt": PROMPTS[object_class],
            "generation_config": {
                "model": "models/sdxl-base",
                "lora": "loras/main-posts/pytorch_lora_weights.safetensors",
                "lora_scale": 0.5,
                "seed": 917364,
                "strength": 0.25,
                "steps": 35,
                "guidance_scale": 7.0,
                "padding_mask_crop": 64,
            },
            "fixture_hashes": {
                "source_sha256": sha256(source_path),
                "mask_sha256": sha256(mask_path),
                "guide_sha256": sha256(guide_path) if guide_path else None,
            },
            "preparation_timing": {
                "automated_mask_guide_preparation_seconds": preparation_seconds,
                "manual_selection_and_region_design_seconds": "NOT_MEASURED_PER_CASE",
            },
        })
    completed_at = datetime.now(timezone.utc).astimezone().isoformat()
    manifest = {
        "schema_version": 1,
        "suite_id": "stage2-v1-descriptive-reliability",
        "suite_kind": "production_validation",
        "study_role": "descriptive_reliability_calibration",
        "execution_status": "PREFLIGHT_PASSED_AWAITING_EXPLICIT_GPU_APPROVAL",
        "preparation_started_at": args.started_at,
        "preparation_completed_at": completed_at,
        "selection_policy": {
            "included": "distinct internally generated fantasy character/scene assets with visible localized target regions",
            "excluded": ["external stock/photo", "deep TikTok/reel frames", "title/text promo cards", "LoRA grids", "empty background keyframes", "duplicate source hashes"],
            "cross_ip_limitation": "EN-heavy; HA and HP included; SF stock/photo fallback excluded; cross-IP generalization NOT_ESTABLISHED",
        },
        "cases": cases,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    timing_path = args.manifest.with_name("stage2-validation-v1-preparation-timing.json")
    timing_path.write_text(json.dumps({"scope": "automated mask/guide materialization only", "rows": prep_rows}, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "manifest": str(args.manifest), "completed_at": completed_at}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
