"""Image Pipeline V2 M4 — ComfyUI adapter (out-of-process, non-GPU qualification).

M4 boundary (per authority record + M3 role freeze):
- Consumes ONLY the M1 GenerationSpec. It does NOT import ComfyUI, does NOT
  depend on Open Design, and ignores Open Design internals.
- This module is the V2 execution adapter: it turns a resolved GenerationSpec
  into a ComfyUI workflow via versioned, hashed templates, submits through the
  ComfyUI REST/WS API, and extracts structured provenance.
- GPU generation is NOT performed here. Actual inference requires a separate
  bounded GPU authority; the adapter only builds + submits + extracts.

Security note: the custom-node security scan is read-only and enumerates the
ComfyUI `custom_nodes/` directory without executing anything.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.generation_spec import GenerationSpec, validate_generation_spec

# --- M4 firewall (binding for M4) ------------------------------------------
# M4 must not pull in Open Design or any rendering-ownership concern.
OPEN_DESIGN_DEPENDENCY = False
CONSUMES_GENERATION_SPEC = True
M4_GPU_AUTHORIZED = False

_TEMPLATE_DIR = Path(__file__).resolve().parent / "workflow_templates"
_DEFAULT_BASE_URL = "http://127.0.0.1:8188"


# --------------------------------------------------------------------------- #
# Workflow template + registry (versioned, hashed)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkflowTemplate:
    template_id: str
    version: str
    description: str
    nodes: Dict[str, Any]
    semantic_inputs: Dict[str, Dict[str, str]]
    sha256: str


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _template_sha256(nodes: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(nodes).encode("utf-8")).hexdigest()


def load_template(template_id: str) -> WorkflowTemplate:
    path = _TEMPLATE_DIR / f"{template_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"workflow template not found: {template_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("v2_meta", {})
    nodes = data["nodes"]
    return WorkflowTemplate(
        template_id=meta.get("id", template_id),
        version=meta.get("version", "0.0"),
        description=meta.get("description", ""),
        nodes=nodes,
        semantic_inputs=meta.get("semantic_inputs", {}),
        sha256=_template_sha256(nodes),
    )


def list_templates() -> List[str]:
    if not _TEMPLATE_DIR.exists():
        return []
    return sorted(p.stem for p in _TEMPLATE_DIR.glob("*.json"))


# --------------------------------------------------------------------------- #
# GenerationSpec -> ComfyUI workflow (deterministic)
# --------------------------------------------------------------------------- #


def _build_positive_prompt(spec: GenerationSpec) -> str:
    bits: List[str] = []
    if spec.style.style_profile:
        bits.append(spec.style.style_profile)
    if spec.style.palette:
        bits.append(spec.style.palette)
    if spec.content.environment:
        bits.append(spec.content.environment)
    if spec.conditioning.object_identity:
        bits.append(spec.conditioning.object_identity)
    if spec.content.props:
        bits.append(", ".join(spec.content.props))
    if spec.attachment.required_visible_evidence:
        bits.append("; ".join(spec.attachment.required_visible_evidence))
    return ", ".join(b for b in bits if b)


def _build_negative_prompt(spec: GenerationSpec) -> str:
    return ", ".join(spec.conditioning.negative_constraints)


def build_workflow(
    template: WorkflowTemplate,
    spec: GenerationSpec,
    seed: Optional[int] = None,
    refs: Tuple[Any, ...] = (),
    masks: Tuple[Any, ...] = (),
) -> Dict[str, Any]:
    """Resolve a GenerationSpec into a runnable ComfyUI workflow.

    Deterministic: same (template, spec, seed, refs, masks) -> identical nodes.
    Consumes only GenerationSpec fields; never touches Open Design.
    """
    validate_generation_spec(spec)  # fail-closed before building
    nodes = json.loads(_canonical_json(template.nodes))  # deep copy

    def set_input(semantic: str, value: Any) -> None:
        mapping = template.semantic_inputs.get(semantic)
        if not mapping:
            return
        node_id = mapping["node"]
        if node_id not in nodes:
            return
        nodes[node_id]["inputs"][mapping["input"]] = value

    set_input("positive_prompt", _build_positive_prompt(spec))
    set_input("negative_prompt", _build_negative_prompt(spec))
    set_input("checkpoint", spec.model_execution.checkpoint)
    set_input("seed", seed if seed is not None else spec.run.seed)
    set_input("steps", spec.model_execution.steps)
    set_input("cfg", spec.model_execution.cfg)
    set_input("sampler", spec.model_execution.sampler)
    set_input("scheduler", spec.model_execution.scheduler)
    set_input("width", spec.model_execution.resolution[0])
    set_input("height", spec.model_execution.resolution[1])

    # LoRAs: list of {name, weight} (modern ComfyUI LoraLoader `lora` input).
    lora_struct = [
        {"name": l.name, "weight": l.weight} for l in spec.model_execution.loras
    ]
    set_input("loras", lora_struct)

    # Optional refs/masks (ControlNet / IP-Adapter / mask) only when supplied.
    if refs:
        set_input("ipadapter", refs[0].asset_path if hasattr(refs[0], "asset_path") else str(refs[0]))
    if masks:
        set_input("mask", masks[0].asset_path if hasattr(masks[0], "asset_path") else str(masks[0]))

    return nodes


# --------------------------------------------------------------------------- #
# Provenance extraction (structured, hashable)
# --------------------------------------------------------------------------- #


def extract_provenance(
    template: WorkflowTemplate,
    built_workflow: Dict[str, Any],
    spec: GenerationSpec,
) -> Dict[str, Any]:
    """Independent, structured provenance for a built workflow.

    Mirrors the V2 manifest principle: the Automation Tool owns provenance, not
    ComfyUI-native metadata alone.
    """
    return {
        "workflow_id": template.template_id,
        "workflow_version": template.version,
        "workflow_sha256": template.sha256,
        "built_workflow_sha256": hashlib.sha256(
            _canonical_json(built_workflow).encode("utf-8")
        ).hexdigest(),
        "spec_version": spec.spec_version,
        "pipeline": spec.style.pipeline,
        "seed": spec.run.seed,
        "checkpoint": spec.model_execution.checkpoint,
        "checkpoint_hash": spec.model_execution.checkpoint_hash,
        "loras": [
            {"name": l.name, "hash": l.hash, "weight": l.weight}
            for l in spec.model_execution.loras
        ],
        "resolution": list(spec.model_execution.resolution),
        "object_state": spec.conditioning.object_state,
        "open_design_dependency": OPEN_DESIGN_DEPENDENCY,
    }


# --------------------------------------------------------------------------- #
# Out-of-process ComfyUI client (never imports ComfyUI)
# --------------------------------------------------------------------------- #


class ComfyUIAdapter:
    """REST/WS client for a running ComfyUI instance.

    Out-of-process only (urllib). No ComfyUI import. Submitting a workflow is an
    execution action and MUST NOT be called under M4 (GPU prohibited); the method
    exists so the eventual GPU-gated execution path is wired through one place.
    """

    def __init__(self, base_url: str = _DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def system_stats(self) -> Dict[str, Any]:
        return self._get("/system_stats")

    def queue_status(self) -> Dict[str, Any]:
        return self._get("/queue")

    def submit_workflow(self, workflow_dict: Dict[str, Any],
                        client_id: Optional[str] = None) -> str:
        """POST /prompt and return the prompt_id. Execution action — GPU-gated."""
        if not M4_GPU_AUTHORIZED:
            raise RuntimeError(
                "ComfyUIAdapter.submit_workflow requires GPU authority (M4_GPU_AUTHORIZED); "
                "blocked under non-GPU M4 qualification."
            )
        body = {"prompt": workflow_dict}
        if client_id:
            body["client_id"] = client_id
        result = self._post("/prompt", body)
        return result["prompt_id"]

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        return self._get(f"/history/{prompt_id}")

    def get_image(self, subfolder: str, filename: str,
                  img_type: str = "output") -> bytes:
        url = f"{self.base_url}/view?subfolder={subfolder}&filename={filename}&type={img_type}"
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            return r.read()


# --------------------------------------------------------------------------- #
# Custom-node security scan (read-only)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CustomNodeFinding:
    name: str
    has_license: bool
    has_git: bool
    network_risk: bool
    notes: str = ""


_NETWORK_IMPORTS = ("urllib", "requests", "socket", "httpx", "aiohttp", "subprocess", "os.system")


def custom_node_security_scan(custom_nodes_dir: str) -> Dict[str, Any]:
    """Read-only enumeration + heuristic risk scan of ComfyUI custom nodes.

    Returns a structured report; performs no execution. A node is flagged
    network_risk when its Python sources import network/subprocess primitives.
    """
    root = Path(custom_nodes_dir)
    findings: List[CustomNodeFinding] = []
    if root.exists():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name in ("__pycache__",):
                continue
            has_license = any((entry / lic).exists() for lic in
                              ("LICENSE", "LICENSE.md", "LICENSE.txt"))
            has_git = (entry / ".git").exists()
            network_risk = False
            note = ""
            py_files = list(entry.rglob("*.py"))
            for pf in py_files:
                try:
                    text = pf.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if any(token in text for token in _NETWORK_IMPORTS):
                    network_risk = True
                    note = f"network/subprocess primitive in {pf.name}"
                    break
            findings.append(CustomNodeFinding(
                name=entry.name, has_license=has_license,
                has_git=has_git, network_risk=network_risk, notes=note,
            ))
    passed = all(not f.network_risk for f in findings)
    return {
        "scanned_dir": str(root),
        "node_count": len(findings),
        "findings": [f.__dict__ for f in findings],
        "passed": passed,
    }
