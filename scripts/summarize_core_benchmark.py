from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from goldevidencebench import schema_validation
from goldevidencebench.core_benchmark import (
    render_core_benchmark_report,
    summarize_core_benchmark,
)


def _write_compact_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a core benchmark run.")
    parser.add_argument(
        "--config",
        default="configs/core_benchmark.json",
        help="Path to core benchmark config JSON.",
    )
    parser.add_argument("--runs-dir", required=True, help="Runs directory to summarize.")
    parser.add_argument("--out", help="Optional output summary JSON path.")
    parser.add_argument("--report", help="Optional output report.md path.")
    parser.add_argument("--min-policy-pass", type=float, help="Fail if policy pass rate < min.")
    parser.add_argument("--min-greedy-pass", type=float, help="Fail if greedy pass rate < min.")
    parser.add_argument("--min-sa-pass", type=float, help="Fail if SA pass rate < min.")
    args = parser.parse_args()

    config_path = Path(args.config)
    runs_dir = Path(args.runs_dir)
    summary = summarize_core_benchmark(config_path, runs_dir)

    thresholds = {}
    if args.min_policy_pass is not None:
        thresholds["policy_task_pass_rate"] = args.min_policy_pass
    if args.min_greedy_pass is not None:
        thresholds["greedy_task_pass_rate"] = args.min_greedy_pass
    if args.min_sa_pass is not None:
        thresholds["sa_task_pass_rate"] = args.min_sa_pass

    failures = []
    if thresholds:
        for entry in summary.get("results", []):
            if not isinstance(entry, dict) or entry.get("status") != "ok":
                continue
            fixture_id = entry.get("id", "")
            policy_rate = entry.get("policy_task_pass_rate")
            greedy_rate = entry.get("greedy_task_pass_rate")
            sa_rate = entry.get("sa_task_pass_rate")
            if args.min_policy_pass is not None:
                if not isinstance(policy_rate, (int, float)) or policy_rate < args.min_policy_pass:
                    failures.append(
                        {"id": fixture_id, "reason": f"policy_task_pass_rate < {args.min_policy_pass}"}
                    )
            if args.min_greedy_pass is not None:
                if not isinstance(greedy_rate, (int, float)) or greedy_rate < args.min_greedy_pass:
                    failures.append(
                        {"id": fixture_id, "reason": f"greedy_task_pass_rate < {args.min_greedy_pass}"}
                    )
            if args.min_sa_pass is not None:
                if not isinstance(sa_rate, (int, float)) or sa_rate < args.min_sa_pass:
                    failures.append(
                        {"id": fixture_id, "reason": f"sa_task_pass_rate < {args.min_sa_pass}"}
                    )

        summary["thresholds"] = thresholds
        summary["failures"] = failures
        summary["status"] = "PASS" if not failures else "FAIL"

    schema_validation.validate_or_raise(
        summary,
        schema_validation.schema_path("core_benchmark_summary.schema.json"),
    )
    out_path = Path(args.out) if args.out else runs_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_text = render_core_benchmark_report(summary)
    report_path = Path(args.report) if args.report else runs_dir / "report.md"
    report_path.write_text(report_text, encoding="utf-8")

    compact_rows: list[dict[str, object]] = []
    for entry in summary.get("results", []):
        if not isinstance(entry, dict):
            continue
        compact_rows.append(
            {
                "id": entry.get("id"),
                "label": entry.get("label"),
                "failure_mode": entry.get("failure_mode"),
                "policy_task_pass_rate": entry.get("policy_task_pass_rate"),
                "greedy_task_pass_rate": entry.get("greedy_task_pass_rate"),
                "sa_task_pass_rate": entry.get("sa_task_pass_rate"),
                "status": entry.get("status"),
            }
        )
    compact_summary = {
        "benchmark": summary.get("benchmark"),
        "runs_dir": summary.get("runs_dir"),
        "generated_at": summary.get("generated_at"),
        "status": summary.get("status"),
        "thresholds": summary.get("thresholds"),
        "means": summary.get("means"),
        "fixtures": compact_rows,
    }
    compact_json_path = out_path.with_name("summary_compact.json")
    compact_csv_path = out_path.with_name("summary_compact.csv")
    compact_json_path.write_text(json.dumps(compact_summary, indent=2), encoding="utf-8")
    _write_compact_csv(
        compact_csv_path,
        compact_rows,
        [
            "id",
            "label",
            "failure_mode",
            "policy_task_pass_rate",
            "greedy_task_pass_rate",
            "sa_task_pass_rate",
            "status",
        ],
    )

    print(f"Wrote {out_path}")
    print(f"Wrote {report_path}")
    if failures:
        print("Core benchmark failed thresholds.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
