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


def _select_rows(
    rows: list[dict[str, Any]],
    *,
    max_rows: int,
    cover_reasons: bool,
    cover_keys: bool,
) -> tuple[list[dict[str, Any]], int, int]:
    if max_rows <= 0:
        return [], 0, 0
    candidates = [row for row in rows if isinstance(row, dict)]
    if not candidates:
        return [], 0, 0

    target_sets = [_targets(row, cover_reasons=cover_reasons, cover_keys=cover_keys) for row in candidates]
    full_targets = set().union(*target_sets)
    remaining = set(full_targets)
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

    covered = len(full_targets - remaining)
    return chosen, covered, len(full_targets)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select a compact counterexample set from a failure drilldown JSONL "
            "(greedy target coverage + shortest-row fill)."
        )
    )
    parser.add_argument("--drilldown", required=True, type=Path, help="Failure drilldown JSONL path.")
    parser.add_argument("--out", required=True, type=Path, help="Output JSONL for minimized rows.")
    parser.add_argument("--max-rows", type=int, default=8, help="Maximum rows to keep.")
    parser.add_argument(
        "--cover-by",
        choices=["reason", "key", "both"],
        default="both",
        help="Coverage targets used during greedy minimization.",
    )
    parser.add_argument(
        "--include-passes",
        action="store_true",
        help="Include rows where exact_ok is true (default: failures only).",
    )
    return parser.parse_args()


def main() -> int:
    ns = _parse_args()
    rows = list(read_jsonl(ns.drilldown))
    if not ns.include_passes:
        rows = [row for row in rows if not bool(row.get("exact_ok"))]
    if not rows:
        write_jsonl(ns.out, [])
        print(f"Wrote 0 rows to {ns.out} (no failures found).")
        return 0

    cover_reasons = ns.cover_by in {"reason", "both"}
    cover_keys = ns.cover_by in {"key", "both"}
    selected, covered, total = _select_rows(
        rows,
        max_rows=ns.max_rows,
        cover_reasons=cover_reasons,
        cover_keys=cover_keys,
    )
    write_jsonl(ns.out, selected)
    coverage_pct = (100.0 * covered / total) if total else 100.0
    print(
        f"Wrote {len(selected)} rows to {ns.out} "
        f"(coverage {covered}/{total} = {coverage_pct:.1f}%)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
