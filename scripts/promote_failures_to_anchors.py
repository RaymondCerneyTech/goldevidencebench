from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl, write_jsonl


def _reasons(row: dict[str, Any]) -> list[str]:
    reasons = row.get("reasons")
    if isinstance(reasons, list):
        cleaned = [str(value) for value in reasons if value]
        if cleaned:
            return cleaned
    return ["unspecified_failure"]


def _key(row: dict[str, Any]) -> str | None:
    value = row.get("key")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _targets(row: dict[str, Any], *, cover_reasons: bool, cover_keys: bool) -> set[str]:
    targets: set[str] = set()
    if cover_reasons:
        targets.update(f"reason:{reason}" for reason in _reasons(row))
    if cover_keys:
        key = _key(row)
        if key:
            targets.add(f"key:{key}")
    if not targets:
        rid = row.get("id")
        targets.add(f"id:{rid}" if rid else "id:unknown")
    return targets


def _cost(row: dict[str, Any]) -> tuple[int, int, str]:
    question = str(row.get("question") or "")
    reasons = _reasons(row)
    rid = str(row.get("id") or "")
    return (len(question), len(reasons), rid)


def _select_failures(
    rows: list[dict[str, Any]],
    *,
    max_rows: int,
    cover_reasons: bool,
    cover_keys: bool,
) -> list[dict[str, Any]]:
    if max_rows <= 0:
        return []
    candidates = [row for row in rows if isinstance(row, dict)]
    if not candidates:
        return []

    target_sets = [_targets(row, cover_reasons=cover_reasons, cover_keys=cover_keys) for row in candidates]
    remaining = set().union(*target_sets)
    chosen: list[dict[str, Any]] = []
    used: set[int] = set()

    while remaining and len(chosen) < max_rows:
        best_idx = None
        best_gain = -1
        best_cost = None
        for idx, row in enumerate(candidates):
            if idx in used:
                continue
            gain = len(target_sets[idx] & remaining)
            cost = _cost(row)
            if gain > best_gain or (gain == best_gain and (best_cost is None or cost < best_cost)):
                best_idx = idx
                best_gain = gain
                best_cost = cost
        if best_idx is None or best_gain <= 0:
            break
        used.add(best_idx)
        chosen.append(candidates[best_idx])
        remaining -= target_sets[best_idx]

    if len(chosen) < max_rows:
        leftovers = [idx for idx in range(len(candidates)) if idx not in used]
        leftovers.sort(key=lambda idx: _cost(candidates[idx]))
        for idx in leftovers:
            if len(chosen) >= max_rows:
                break
            chosen.append(candidates[idx])

    return chosen


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Promote drilldown failures into anchor candidate fixtures by selecting a "
            "small, high-coverage failure subset and exporting matching source rows."
        )
    )
    parser.add_argument("--data", required=True, type=Path, help="Source dataset JSONL.")
    parser.add_argument("--drilldown", required=True, type=Path, help="Failure drilldown JSONL.")
    parser.add_argument("--out", required=True, type=Path, help="Anchor candidate JSONL path.")
    parser.add_argument("--max-anchors", type=int, default=8, help="Maximum anchor rows to write.")
    parser.add_argument(
        "--cover-by",
        choices=["reason", "key", "both"],
        default="both",
        help="Coverage targets used during failure selection.",
    )
    parser.add_argument(
        "--include-passes",
        action="store_true",
        help="Include rows where exact_ok is true (default: failures only).",
    )
    parser.add_argument(
        "--family",
        default=None,
        help="Optional trap family tag stored in row meta as promoted_trap_family.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing output (deduplicated by row id).",
    )
    return parser.parse_args()


def main() -> int:
    ns = _parse_args()
    source_rows = [row for row in read_jsonl(ns.data) if isinstance(row, dict)]
    source_by_id = {str(row.get("id")): row for row in source_rows if row.get("id")}

    failures = [row for row in read_jsonl(ns.drilldown) if isinstance(row, dict)]
    if not ns.include_passes:
        failures = [row for row in failures if not bool(row.get("exact_ok"))]
    if not failures:
        write_jsonl(ns.out, [])
        print(f"Wrote 0 rows to {ns.out} (no failures found).")
        return 0

    cover_reasons = ns.cover_by in {"reason", "both"}
    cover_keys = ns.cover_by in {"key", "both"}
    selected_failures = _select_failures(
        failures,
        max_rows=ns.max_anchors,
        cover_reasons=cover_reasons,
        cover_keys=cover_keys,
    )

    promoted: list[dict[str, Any]] = []
    missing_ids: list[str] = []
    for failure in selected_failures:
        row_id = failure.get("id")
        if row_id is None:
            continue
        source = source_by_id.get(str(row_id))
        if source is None:
            missing_ids.append(str(row_id))
            continue
        promoted_row = dict(source)
        meta = dict(promoted_row.get("meta") or {})
        meta["promoted_from"] = str(ns.drilldown)
        meta["promoted_failure_reasons"] = _reasons(failure)
        if ns.family:
            meta["promoted_trap_family"] = ns.family
        promoted_row["meta"] = meta
        promoted.append(promoted_row)

    if ns.append and ns.out.exists():
        existing = [row for row in read_jsonl(ns.out) if isinstance(row, dict)]
        merged: dict[str, dict[str, Any]] = {}
        for row in existing + promoted:
            row_id = row.get("id")
            if row_id is None:
                continue
            merged[str(row_id)] = row
        promoted = list(merged.values())

    write_jsonl(ns.out, promoted)
    if missing_ids:
        print(f"Warning: missing {len(missing_ids)} source rows for ids: {', '.join(missing_ids)}")
    print(f"Wrote {len(promoted)} rows to {ns.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
