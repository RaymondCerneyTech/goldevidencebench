from __future__ import annotations

import argparse
from pathlib import Path

from goldevidencebench.ui_fixture import validate_ui_fixture_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate UI fixture schema.")
    parser.add_argument(
        "--fixture",
        default="data/ui_same_label_fixture.jsonl",
        help="Path to the UI fixture JSONL file.",
    )
    args = parser.parse_args()
    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Fixture not found: {fixture_path}")
        return 1

    errors = validate_ui_fixture_path(fixture_path)
    if errors:
        print("Fixture validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Fixture OK: {fixture_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
