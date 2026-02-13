from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate persona invariance across trap-family reliability candidates "
            "and enforce row_invariance_rate == 1.0."
        )
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Input mappings in the form family_id=path_to_reliability_summary.json.",
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rows-out", required=True, type=Path)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _parse_inputs(items: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --inputs entry (expected family=path): {item}")
        family, path_text = item.split("=", 1)
        family = family.strip()
        path_text = path_text.strip()
        if not family or not path_text:
            raise ValueError(f"Invalid --inputs entry: {item}")
        out[family] = Path(path_text)
    return out


def _find_combined_summary(run_dir: Path, family: str) -> Path | None:
    preferred = run_dir / f"{family}_summary.json"
    if preferred.exists():
        return preferred

    if family == "compression_families":
        comp = run_dir / "compression_families_summary.json"
        if comp.exists():
            return comp

    candidates: list[Path] = []
    for path in sorted(run_dir.glob("*_summary.json")):
        name = path.name.lower()
        if name in {"anchors_summary.json", "holdout_summary.json", "canary_summary.json"}:
            continue
        candidates.append(path)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _to_rate(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_persona_rows(*, family: str, run_dir: Path, summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    benchmark = str(summary.get("benchmark") or family)

    if benchmark == "compression_families":
        families = summary.get("families")
        if not isinstance(families, dict):
            rows.append(
                {
                    "family": family,
                    "component": family,
                    "run_dir": str(run_dir),
                    "summary_path": None,
                    "row_invariance_rate": None,
                    "rows_total": None,
                    "rows_changed": None,
                    "status": "FAIL",
                    "reason": "missing_families_object",
                }
            )
            return rows
        for subfamily, payload in sorted(families.items()):
            persona = payload.get("persona_invariance") if isinstance(payload, dict) else None
            rate = _to_rate(persona.get("row_invariance_rate")) if isinstance(persona, dict) else None
            rows_total = int(_to_rate(persona.get("rows_total")) or 0) if isinstance(persona, dict) else 0
            rows_changed = int(_to_rate(persona.get("rows_changed")) or 0) if isinstance(persona, dict) else 0
            status = "PASS" if rate is not None and abs(rate - 1.0) <= 1e-12 else "FAIL"
            reason = None if status == "PASS" else "persona_contract_drift"
            rows.append(
                {
                    "family": family,
                    "component": str(subfamily),
                    "run_dir": str(run_dir),
                    "summary_path": str(run_dir / f"{family}_summary.json"),
                    "row_invariance_rate": rate,
                    "rows_total": rows_total,
                    "rows_changed": rows_changed,
                    "status": status,
                    "reason": reason,
                }
            )
        return rows

    persona = summary.get("persona_invariance")
    rate = _to_rate(persona.get("row_invariance_rate")) if isinstance(persona, dict) else None
    rows_total = int(_to_rate(persona.get("rows_total")) or 0) if isinstance(persona, dict) else 0
    rows_changed = int(_to_rate(persona.get("rows_changed")) or 0) if isinstance(persona, dict) else 0
    status = "PASS" if rate is not None and abs(rate - 1.0) <= 1e-12 else "FAIL"
    reason = None if status == "PASS" else "persona_contract_drift"
    rows.append(
        {
            "family": family,
            "component": family,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / f"{family}_summary.json"),
            "row_invariance_rate": rate,
            "rows_total": rows_total,
            "rows_changed": rows_changed,
            "status": status,
            "reason": reason,
        }
    )
    return rows


def main() -> int:
    ns = _parse_args()
    inputs = _parse_inputs(ns.inputs)
    rows_out: list[dict[str, Any]] = []
    failures: list[str] = []

    for family, reliability_path in sorted(inputs.items()):
        reliability = _read_json(reliability_path)
        if reliability is None:
            failures.append(f"{family}: missing_or_invalid_reliability_summary ({reliability_path})")
            rows_out.append(
                {
                    "family": family,
                    "component": family,
                    "run_dir": None,
                    "summary_path": None,
                    "row_invariance_rate": None,
                    "rows_total": None,
                    "rows_changed": None,
                    "status": "FAIL",
                    "reason": "missing_or_invalid_reliability_summary",
                }
            )
            continue

        runs = reliability.get("runs")
        if not isinstance(runs, list) or not runs:
            failures.append(f"{family}: reliability_summary_missing_runs ({reliability_path})")
            rows_out.append(
                {
                    "family": family,
                    "component": family,
                    "run_dir": None,
                    "summary_path": None,
                    "row_invariance_rate": None,
                    "rows_total": None,
                    "rows_changed": None,
                    "status": "FAIL",
                    "reason": "reliability_summary_missing_runs",
                }
            )
            continue

        for run_item in runs:
            run_dir = Path(str(run_item))
            summary_path = _find_combined_summary(run_dir, family)
            if summary_path is None:
                failures.append(f"{family}: missing_combined_summary ({run_dir})")
                rows_out.append(
                    {
                        "family": family,
                        "component": family,
                        "run_dir": str(run_dir),
                        "summary_path": None,
                        "row_invariance_rate": None,
                        "rows_total": None,
                        "rows_changed": None,
                        "status": "FAIL",
                        "reason": "missing_combined_summary",
                    }
                )
                continue

            combined = _read_json(summary_path)
            if combined is None:
                failures.append(f"{family}: invalid_combined_summary ({summary_path})")
                rows_out.append(
                    {
                        "family": family,
                        "component": family,
                        "run_dir": str(run_dir),
                        "summary_path": str(summary_path),
                        "row_invariance_rate": None,
                        "rows_total": None,
                        "rows_changed": None,
                        "status": "FAIL",
                        "reason": "invalid_combined_summary",
                    }
                )
                continue

            rows_out.extend(_extract_persona_rows(family=family, run_dir=run_dir, summary=combined))

    family_rollup: dict[str, dict[str, Any]] = {}
    for row in rows_out:
        family = str(row.get("family") or "")
        item = family_rollup.setdefault(
            family,
            {
                "family": family,
                "status": "PASS",
                "runs_checked": 0,
                "components_checked": 0,
                "min_row_invariance_rate": None,
                "rows_total": 0,
                "rows_changed": 0,
            },
        )
        if row.get("run_dir"):
            item["runs_checked"] = int(item["runs_checked"]) + 1
        item["components_checked"] = int(item["components_checked"]) + 1
        rate = _to_rate(row.get("row_invariance_rate"))
        if rate is None:
            item["status"] = "FAIL"
        else:
            min_rate = item["min_row_invariance_rate"]
            if min_rate is None or rate < float(min_rate):
                item["min_row_invariance_rate"] = rate
            if abs(rate - 1.0) > 1e-12:
                item["status"] = "FAIL"
        item["rows_total"] = int(item["rows_total"]) + int(_to_rate(row.get("rows_total")) or 0)
        item["rows_changed"] = int(item["rows_changed"]) + int(_to_rate(row.get("rows_changed")) or 0)

    family_summaries = [family_rollup[key] for key in sorted(family_rollup)]
    explicit_failures = [row for row in rows_out if row.get("status") == "FAIL"]
    min_rate_values = [
        float(row["row_invariance_rate"])
        for row in rows_out
        if _to_rate(row.get("row_invariance_rate")) is not None
    ]
    min_row_invariance_rate = min(min_rate_values) if min_rate_values else 0.0
    overall_rows_total = sum(int(_to_rate(row.get("rows_total")) or 0) for row in rows_out)
    overall_rows_changed = sum(int(_to_rate(row.get("rows_changed")) or 0) for row in rows_out)
    status = "PASS" if not failures and not explicit_failures else "FAIL"

    summary = {
        "benchmark": "persona_invariance_gate",
        "status": status,
        "failure_category": "persona_contract_drift",
        "threshold": {"row_invariance_rate": 1.0},
        "overall": {
            "families_total": len(inputs),
            "families_checked": len(family_summaries),
            "rows_total": overall_rows_total,
            "rows_changed": overall_rows_changed,
            "min_row_invariance_rate": min_row_invariance_rate,
        },
        "families": family_summaries,
        "failures": failures
        + [
            f"{row.get('family')}:{row.get('component')}@{row.get('run_dir')} -> {row.get('reason')}"
            for row in explicit_failures
        ],
    }

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.rows_out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_jsonl(ns.rows_out, rows_out)

    print("Persona invariance release gate")
    print(f"Families input: {len(inputs)}")
    print(f"Rows checked: {len(rows_out)}")
    print(f"Min row_invariance_rate: {min_row_invariance_rate:.6f}")
    print(f"RESULT: {status}")
    print(f"Wrote {ns.out}")
    print(f"Wrote {ns.rows_out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
