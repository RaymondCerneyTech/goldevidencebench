from __future__ import annotations

import json
from pathlib import Path

from goldevidencebench import schema_validation


def _write_schema(path: Path, schema: dict) -> Path:
    path.write_text(json.dumps(schema), encoding="utf-8")
    return path


def test_schema_validation_required_and_type(tmp_path: Path) -> None:
    schema_path = _write_schema(
        tmp_path / "schema.json",
        {
            "type": "object",
            "required": ["name", "count"],
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
        },
    )
    ok = {"name": "run", "count": 3}
    errors = schema_validation.validate_artifact(ok, schema_path)
    assert errors == []

    bad = {"name": "run"}
    errors = schema_validation.validate_artifact(bad, schema_path)
    assert errors and "missing required 'count'" in errors[0]


def test_schema_validation_union_type(tmp_path: Path) -> None:
    schema_path = _write_schema(
        tmp_path / "schema.json",
        {
            "type": "object",
            "required": ["optional_field"],
            "properties": {
                "optional_field": {"type": ["string", "null"]},
            },
        },
    )
    errors = schema_validation.validate_artifact({"optional_field": None}, schema_path)
    assert errors == []
