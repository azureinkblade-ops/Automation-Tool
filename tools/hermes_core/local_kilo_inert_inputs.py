"""Prepare isolated dummy Kilo config files; no container or network access."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Mapping

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


def verified_inert_mount_sources(prepared: Mapping[str, Any]) -> tuple[str, str]:
    """Read back 92DP dummy bytes and derive the two expected bind sources."""
    if (not isinstance(prepared, Mapping)
            or prepared.get("schema_id") != "hermes.local-kilo-inert-inputs/v1"
            or prepared.get("launch_authorized") is not False):
        raise ValueError("invalid inert input manifest")
    root_text = prepared.get("root")
    if not isinstance(root_text, str):
        raise ValueError("invalid inert input root")
    root = Path(root_text)
    temp_root = Path(tempfile.gettempdir()).resolve()
    if (not root.is_absolute() or root.resolve(strict=True) != root
            or root == temp_root or not root.is_relative_to(temp_root)):
        raise ValueError("inert input root escaped temp")

    input_dir = root / "input"
    runtime_dir = root / "runtime"
    if not input_dir.is_dir() or not runtime_dir.is_dir():
        raise ValueError("missing inert input directory")
    if any(path.is_symlink() or path.is_junction() for path in (root, input_dir, runtime_dir)):
        raise ValueError("inert input directory is a link")

    files = prepared.get("files")
    plan = build_inert_plan()
    if not isinstance(files, list) or len(files) != len(plan["planned_files"]):
        raise ValueError("inert input file count mismatch")
    expected = set()
    for linux_path, item in plan["planned_files"].items():
        relative = PurePosixPath(linux_path).relative_to(PurePosixPath(HOME))
        source = input_dir / Path(relative)
        runtime = runtime_dir / Path(relative)
        for path in (source, runtime):
            if path.is_symlink() or path.resolve(strict=True) != path:
                raise ValueError("inert input file is a link")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("inert input byte mismatch")
        expected.add((str(source), str(runtime), item["sha256"]))
    observed = set()
    for item in files:
        if not isinstance(item, Mapping):
            raise ValueError("invalid inert input record")
        observed.add((item.get("input_path"), item.get("runtime_path"), item.get("sha256")))
    if observed != expected:
        raise ValueError("inert input manifest mismatch")
    return str(input_dir), str(runtime_dir)
