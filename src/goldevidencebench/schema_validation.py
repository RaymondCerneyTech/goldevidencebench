from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _schema_root() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas"


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _validate_schema(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        if isinstance(expected, list):
            if not any(_matches_type(value, t) for t in expected):
                errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
                return errors
        else:
            if not _matches_type(value, expected):
                errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
                return errors

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum")
        return errors

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required '{key}'")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                errors.extend(_validate_schema(item, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property '{key}'")

    if isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for idx, item in enumerate(value):
                errors.extend(_validate_schema(item, items_schema, f"{path}[{idx}]"))

    return errors


def validate_artifact(data: dict[str, Any], schema_path: Path) -> list[str]:
    schema = load_schema(schema_path)
    return _validate_schema(data, schema, "$")


def validate_or_raise(data: dict[str, Any], schema_path: Path) -> None:
    errors = validate_artifact(data, schema_path)
    if errors:
        joined = "; ".join(errors)
        raise ValueError(f"Schema validation failed for {schema_path}: {joined}")


def schema_path(name: str) -> Path:
    return _schema_root() / name
