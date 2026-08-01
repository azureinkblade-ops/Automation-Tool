"""Load and validate the lightweight Hermes YAML schema contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class SchemaValidationError(ValueError):
    """Raised when a Hermes document does not satisfy its schema contract."""


@dataclass(frozen=True)
class SchemaCatalog:
    root: Path
    schemas: dict[str, dict[str, Any]]

    def get(self, schema_name: str) -> dict[str, Any]:
        try:
            return self.schemas[schema_name]
        except KeyError as exc:
            raise SchemaValidationError(f"Unknown schema: {schema_name}") from exc

    def validate(self, schema_name: str, document: dict[str, Any]) -> None:
        schema = self.get(schema_name)
        _validate_object(schema_name, schema, document, path=schema_name)


def load_schema_catalog(root: Path | str | None = None) -> SchemaCatalog:
    repo_root = Path(root) if root is not None else Path.cwd()
    schema_dir = repo_root / "docs" / "architecture" / "schemas"
    if not schema_dir.exists():
        raise SchemaValidationError(f"Schema directory not found: {schema_dir}")

    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(schema_dir.glob("*.schema.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SchemaValidationError(f"Schema file is not a mapping: {path}")
        schema_name = data.get("schema")
        if not isinstance(schema_name, str) or not schema_name:
            raise SchemaValidationError(f"Schema file missing schema name: {path}")
        schemas[schema_name] = data

    if not schemas:
        raise SchemaValidationError(f"No schemas found in {schema_dir}")
    return SchemaCatalog(root=repo_root, schemas=schemas)


def _validate_object(
    schema_name: str,
    schema: dict[str, Any],
    value: Any,
    *,
    path: str,
) -> None:
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{path} must be an object")

    for key in schema.get("required", []) or []:
        if key not in value or value[key] is None:
            raise SchemaValidationError(f"{path}.{key} is required")

    fields = schema.get("fields", {}) or {}
    for key, field_schema in fields.items():
        if key not in value or value[key] is None:
            if field_schema.get("nullable") and key in value:
                continue
            continue
        _validate_field(schema_name, field_schema, value[key], path=f"{path}.{key}")


def _validate_field(
    schema_name: str,
    field_schema: dict[str, Any],
    value: Any,
    *,
    path: str,
) -> None:
    if value is None and field_schema.get("nullable"):
        return

    const = field_schema.get("const")
    if "const" in field_schema and value != const:
        raise SchemaValidationError(f"{path} must be {const!r}")

    enum = field_schema.get("enum")
    if enum is not None and value not in enum:
        raise SchemaValidationError(f"{path} must be one of {enum!r}")

    field_type = field_schema.get("type")
    if field_type == "string":
        if not isinstance(value, str):
            raise SchemaValidationError(f"{path} must be a string")
        if field_schema.get("format") == "date-time":
            _validate_datetime(value, path)
    elif field_type == "boolean":
        if not isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be a boolean")
    elif field_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be an integer")
    elif field_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be a number")
        if "minimum" in field_schema and value < field_schema["minimum"]:
            raise SchemaValidationError(f"{path} is below minimum")
        if "maximum" in field_schema and value > field_schema["maximum"]:
            raise SchemaValidationError(f"{path} is above maximum")
    elif field_type == "array":
        if not isinstance(value, list):
            raise SchemaValidationError(f"{path} must be an array")
        item_schema = field_schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_array_item(item_schema, item, path=f"{path}[{index}]")
    elif field_type == "object":
        _validate_object(schema_name, field_schema, value, path=path)


def _validate_array_item(field_schema: dict[str, Any], value: Any, *, path: str) -> None:
    if field_schema.get("type") == "object":
        _validate_object("array_item", field_schema, value, path=path)
    elif field_schema.get("type") == "string" and not isinstance(value, str):
        raise SchemaValidationError(f"{path} must be a string")


def _validate_datetime(value: str, path: str) -> None:
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SchemaValidationError(f"{path} must be an ISO date-time") from exc
