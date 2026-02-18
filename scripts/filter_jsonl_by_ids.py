from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter a JSONL fixture by row IDs.")
    parser.add_argument("--data", required=True, type=Path, help="Input JSONL path.")
    parser.add_argument("--ids", required=True, type=Path, help="Text file with one row ID per line.")
    parser.add_argument("--out", required=True, type=Path, help="Output JSONL path.")
    parser.add_argument(
        "--invert",
        action="store_true",
        help="Write rows whose IDs are NOT in --ids.",
    )
    return parser.parse_args()


def _read_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if value:
            ids.add(value)
    return ids


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def main() -> int:
    ns = _parse_args()
    row_ids = _read_ids(ns.ids)
    if not row_ids:
        print(f"No IDs loaded from {ns.ids}")
        return 1

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    in_count = 0
    out_count = 0
    with ns.out.open("w", encoding="utf-8", newline="\n") as handle:
        for row in _iter_jsonl(ns.data):
            in_count += 1
            row_id_raw: Any = row.get("id")
            row_id = str(row_id_raw).strip() if row_id_raw is not None else ""
            in_set = row_id in row_ids
            keep = (not in_set) if ns.invert else in_set
            if not keep:
                continue
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
            out_count += 1

    print(f"filter_jsonl_by_ids: in_rows={in_count} out_rows={out_count} invert={bool(ns.invert)}")
    return 0 if out_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
