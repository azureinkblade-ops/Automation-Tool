"""Prepare isolated dummy Kilo config files; no container or network access."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import tempfile

from tools.hermes_core.local_kilo_inert_plan import HOME, build_inert_plan


def prepare_inert_inputs(root: Path) -> dict:
    """Write reviewed input and separate runtime copies under a new temp root."""
    root = Path(root).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if root == temp_root or not root.is_relative_to(temp_root) or root.exists():
        raise ValueError("root must be new and under the system temp directory")
    if not root.parent.is_dir():
        raise ValueError("root parent must already exist")

    plan = build_inert_plan()
    prepared = []
    for linux_path, item in plan["planned_files"].items():
        relative = PurePosixPath(linux_path).relative_to(PurePosixPath(HOME))
        content = item["content"].encode("ascii")
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("planned input hash mismatch")
        prepared.append((relative, content, item["sha256"]))

    root.mkdir()
    records = []
    for relative, content, digest in prepared:
        input_path = root / "input" / Path(relative)
        runtime_path = root / "runtime" / Path(relative)
        input_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_bytes(content)
        runtime_path.write_bytes(content)
        if (hashlib.sha256(input_path.read_bytes()).hexdigest() != digest
                or hashlib.sha256(runtime_path.read_bytes()).hexdigest() != digest):
            raise ValueError("staged input hash mismatch")
        records.append({
            "input_path": str(input_path),
            "runtime_path": str(runtime_path),
            "sha256": digest,
        })

    return {
        "schema_id": "hermes.local-kilo-inert-inputs/v1",
        "root": str(root),
        "files": records,
        "launch_authorized": False,
    }
