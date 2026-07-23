"""Storage inventory and manifest for the SQLite consolidation effort.

SC-1 scope only: classify every root-level JSON and logical state object so
later stages can migrate durable state and quarantine dead files safely.

This package is read-only for live state. It never writes app JSON or the
live automation_state.db. Do not import app.py here.
"""

from .audit_storage_resources import (
    build_inventory_report,
    root_json_inventory,
    scan_repository,
)
from .resource_manifest import (
    CLASSIFICATIONS,
    ResourceClassification,
    StorageResource,
    STATE_RESOURCES,
    classify_root_json,
    load_manifest,
)

__all__ = [
    "CLASSIFICATIONS",
    "ResourceClassification",
    "StorageResource",
    "STATE_RESOURCES",
    "classify_root_json",
    "load_manifest",
    "scan_repository",
    "root_json_inventory",
    "build_inventory_report",
]
