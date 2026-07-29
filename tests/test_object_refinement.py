from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_disabled_refinement_returns_original_without_calling_backend(tmp_path, monkeypatch):
    from object_refinement import ObjectRefinementService, RefinementRequest

    monkeypatch.delenv("VISUAL_OBJECT_REFINEMENT_ENABLED", raising=False)
    source = tmp_path / "source.png"
    source.write_bytes(b"source")
    mask = tmp_path / "mask.png"
    mask.write_bytes(b"mask")
    called = False

    def backend(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("disabled service must not invoke backend")

    request = RefinementRequest(
        object_type="jian",
        target_region="outer left hip",
        prompt="one sheathed Chinese jian",
        mask_path=mask,
    )
    result = ObjectRefinementService(backend=backend).refine(source, request, tmp_path / "work")

    assert result.status == "disabled"
    assert result.output_path == source
    assert result.candidate_path is None
    assert called is False


def test_accepted_refinement_emits_candidate_provenance_and_diff(tmp_path, monkeypatch):
    import app  # establishes this repo's working PIL import path
    from PIL import Image
    from object_refinement import (
        AcceptanceVerdict,
        BackendReceipt,
        ObjectRefinementService,
        RefinementRequest,
    )

    monkeypatch.setenv("VISUAL_OBJECT_REFINEMENT_ENABLED", "1")
    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source)
    mask_image = Image.new("L", (4, 4), 0)
    mask_image.putpixel((1, 1), 255)
    mask_image.save(mask)

    def backend(source_path, request, candidate_path):
        candidate = Image.open(source_path).convert("RGB")
        candidate.putpixel((1, 1), (200, 210, 220))
        candidate.save(candidate_path)
        return BackendReceipt(
            model="test-inpaint",
            seed=7,
            parameters={"strength": 0.25},
        )

    def reviewer(source_path, candidate_path, request):
        return AcceptanceVerdict(accepted=True, reasons=("jian recognizable",))

    request = RefinementRequest(
        object_type="jian",
        target_region="outer left hip",
        prompt="one sheathed Chinese jian",
        mask_path=mask,
    )
    result = ObjectRefinementService(backend=backend, reviewer=reviewer).refine(
        source, request, tmp_path / "work"
    )

    assert result.status == "accepted"
    assert result.output_path == result.candidate_path
    assert result.output_path.exists()
    assert result.provenance_path is not None and result.provenance_path.exists()
    assert result.diff_path is not None and result.diff_path.exists()


def test_outside_mask_change_forces_rejection_and_returns_original(tmp_path, monkeypatch):
    import app
    from PIL import Image
    from object_refinement import (
        AcceptanceVerdict,
        BackendReceipt,
        ObjectRefinementService,
        RefinementRequest,
    )

    monkeypatch.setenv("VISUAL_OBJECT_REFINEMENT_ENABLED", "1")
    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source)
    mask_image = Image.new("L", (4, 4), 0)
    mask_image.putpixel((1, 1), 255)
    mask_image.save(mask)

    def backend(source_path, request, candidate_path):
        candidate = Image.open(source_path).convert("RGB")
        candidate.putpixel((1, 1), (200, 210, 220))
        candidate.putpixel((3, 3), (99, 99, 99))  # outside authorized mask
        candidate.save(candidate_path)
        return BackendReceipt(model="test-inpaint", seed=8, parameters={})

    reviewer = lambda *args: AcceptanceVerdict(accepted=True, reasons=("looks good",))
    request = RefinementRequest("jian", "outer hip", "one jian", mask)
    result = ObjectRefinementService(backend=backend, reviewer=reviewer).refine(
        source, request, tmp_path / "work"
    )

    assert result.status == "rejected"
    assert result.output_path == source
    assert result.candidate_path is not None and result.candidate_path.exists()
    provenance = result.provenance_path.read_text(encoding="utf-8")
    assert '"outside_mask_changed_pixels": 1' in provenance
    assert '"failure_returns_original": true' in provenance


def test_empty_mask_is_rejected_before_backend_execution(tmp_path, monkeypatch):
    import app
    from PIL import Image
    from object_refinement import ObjectRefinementService, RefinementRequest

    monkeypatch.setenv("VISUAL_OBJECT_REFINEMENT_ENABLED", "1")
    source = tmp_path / "source.png"
    mask = tmp_path / "empty-mask.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source)
    Image.new("L", (4, 4), 0).save(mask)
    called = False

    def backend(*args):
        nonlocal called
        called = True
        raise AssertionError("empty mask must fail before backend")

    request = RefinementRequest("jian", "outer hip", "one jian", mask)
    result = ObjectRefinementService(backend=backend, reviewer=lambda *a: None).refine(
        source, request, tmp_path / "work"
    )

    assert result.status == "rejected"
    assert result.output_path == source
    assert result.candidate_path is None
    assert called is False


def test_subprocess_backend_forwards_contract_and_reads_receipt(tmp_path, monkeypatch):
    import json
    import subprocess
    from local_object_refinement_backend import LocalSDXLInpaintBackend
    from object_refinement import RefinementRequest

    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    guide = tmp_path / "guide.png"
    model = tmp_path / "model"
    lora = tmp_path / "weights.safetensors"
    script = tmp_path / "local_object_refiner.py"
    for path in (source, mask, guide, lora, script):
        path.write_bytes(b"x")
    model.mkdir()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"candidate")
        sidecar = output.with_suffix(output.suffix + ".refinement.json")
        sidecar.write_text(json.dumps({
            "model": str(model), "seed": 19,
            "parameters": {"strength": 0.25, "steps": 35},
        }), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = LocalSDXLInpaintBackend(
        python_executable="python",
        script_path=script,
        model_path=model,
        lora_path=lora,
        seed=19,
        strength=0.25,
        steps=35,
    )
    request = RefinementRequest("jian", "outer hip", "one jian", mask, guide)
    receipt = backend(source, request, tmp_path / "candidate.png")

    assert "--guide" in captured["command"]
    assert captured["command"][captured["command"].index("--prompt") + 1] == "one jian"
    assert receipt.model == str(model)
    assert receipt.seed == 19
    assert receipt.parameters["strength"] == 0.25


def test_refiner_composite_preserves_every_outside_mask_pixel(tmp_path):
    import app
    from PIL import Image
    from local_object_refiner import composite_refinement

    source = Image.new("RGB", (3, 3), (10, 20, 30))
    generated = Image.new("RGB", (3, 3), (200, 210, 220))
    mask = Image.new("L", (3, 3), 0)
    mask.putpixel((1, 1), 255)

    result = composite_refinement(source, generated, mask)

    for y in range(3):
        for x in range(3):
            expected = (200, 210, 220) if (x, y) == (1, 1) else (10, 20, 30)
            assert result.getpixel((x, y)) == expected


def test_missing_reviewer_leaves_candidate_pending_and_returns_original(tmp_path, monkeypatch):
    import app
    from PIL import Image
    from object_refinement import BackendReceipt, ObjectRefinementService, RefinementRequest

    monkeypatch.setenv("VISUAL_OBJECT_REFINEMENT_ENABLED", "1")
    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGB", (3, 3), (10, 20, 30)).save(source)
    mask_image = Image.new("L", (3, 3), 0)
    mask_image.putpixel((1, 1), 255)
    mask_image.save(mask)

    def backend(source_path, request, candidate_path):
        candidate = Image.open(source_path).convert("RGB")
        candidate.putpixel((1, 1), (200, 210, 220))
        candidate.save(candidate_path)
        return BackendReceipt(model="test", seed=1, parameters={})

    result = ObjectRefinementService(backend=backend).refine(
        source,
        RefinementRequest("jian", "outer hip", "one jian", mask),
        tmp_path / "work",
    )

    assert result.status == "pending_review"
    assert result.output_path == source
    assert result.candidate_path is not None and result.candidate_path.exists()
    assert result.provenance_path is not None and result.provenance_path.exists()


def test_finalize_pending_review_promotes_hash_verified_candidate(tmp_path, monkeypatch):
    import app
    from PIL import Image
    from object_refinement import (
        AcceptanceVerdict,
        BackendReceipt,
        ObjectRefinementService,
        RefinementRequest,
        finalize_review,
    )

    monkeypatch.setenv("VISUAL_OBJECT_REFINEMENT_ENABLED", "1")
    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGB", (3, 3), (10, 20, 30)).save(source)
    m = Image.new("L", (3, 3), 0)
    m.putpixel((1, 1), 255)
    m.save(mask)

    def backend(source_path, request, candidate_path):
        candidate = Image.open(source_path).convert("RGB")
        candidate.putpixel((1, 1), (200, 210, 220))
        candidate.save(candidate_path)
        return BackendReceipt(model="test", seed=1, parameters={})

    pending = ObjectRefinementService(backend=backend).refine(
        source, RefinementRequest("jian", "hip", "one jian", mask), tmp_path / "work"
    )
    finalized = finalize_review(
        pending.provenance_path,
        AcceptanceVerdict(True, ("jian coherent", "pose preserved")),
    )

    assert finalized.status == "accepted"
    assert finalized.output_path == pending.candidate_path
    assert finalized.provenance_path.name == "final-provenance.json"
    assert '"status": "accepted"' in finalized.provenance_path.read_text(encoding="utf-8")
    assert '"status": "pending_review"' in pending.provenance_path.read_text(encoding="utf-8")
