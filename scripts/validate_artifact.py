from __future__ import annotations

import argparse
import json
from pathlib import Path

from goldevidencebench import schema_validation


def _load_json(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = path.read_text(encoding="utf-8-sig")
        return json.loads(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a JSON artifact against a schema.")
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--path", required=True, type=Path)
    ns = parser.parse_args()

    if not ns.path.exists():
        print(f"Artifact not found: {ns.path}")
        return 1
    if not ns.schema.exists():
        print(f"Schema not found: {ns.schema}")
        return 1

    data = _load_json(ns.path)
    errors = schema_validation.validate_artifact(data, ns.schema)
    if errors:
        print(f"Schema validation failed for {ns.path}:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Schema validation OK: {ns.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
