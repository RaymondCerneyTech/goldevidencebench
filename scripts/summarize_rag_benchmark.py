from __future__ import annotations

import argparse
import json
from pathlib import Path

from goldevidencebench.rag_benchmark import (
    render_rag_benchmark_report,
    summarize_rag_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a RAG benchmark run.")
    parser.add_argument(
        "--config",
        default="configs/rag_benchmark.json",
        help="Path to rag benchmark config JSON.",
    )
    parser.add_argument("--runs-dir", required=True, help="Runs directory to summarize.")
    parser.add_argument("--out", help="Optional output summary JSON path.")
    parser.add_argument("--report", help="Optional output report.md path.")
    parser.add_argument("--min-value-acc", type=float, help="Fail if value_acc < min.")
    parser.add_argument("--min-cite-f1", type=float, help="Fail if cite_f1 < min.")
    parser.add_argument(
        "--min-instruction-acc",
        type=float,
        help="Fail if instruction_acc < min.",
    )
    parser.add_argument(
        "--min-state-integrity",
        type=float,
        help="Fail if state_integrity_rate < min.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    runs_dir = Path(args.runs_dir)
    summary = summarize_rag_benchmark(config_path, runs_dir)

    thresholds = {}
    if args.min_value_acc is not None:
        thresholds["value_acc"] = args.min_value_acc
    if args.min_cite_f1 is not None:
        thresholds["cite_f1"] = args.min_cite_f1
    if args.min_instruction_acc is not None:
        thresholds["instruction_acc"] = args.min_instruction_acc
    if args.min_state_integrity is not None:
        thresholds["state_integrity_rate"] = args.min_state_integrity

    failures = []
    if thresholds:
        for entry in summary.get("results", []):
            if not isinstance(entry, dict) or entry.get("status") != "ok":
                continue
            dataset_id = entry.get("id", "")
            value_acc = entry.get("value_acc")
            cite_f1 = entry.get("cite_f1")
            instruction_acc = entry.get("instruction_acc")
            state_integrity_rate = entry.get("state_integrity_rate")
            if args.min_value_acc is not None:
                if not isinstance(value_acc, (int, float)) or value_acc < args.min_value_acc:
                    failures.append(
                        {"id": dataset_id, "reason": f"value_acc < {args.min_value_acc}"}
                    )
            if args.min_cite_f1 is not None:
                if not isinstance(cite_f1, (int, float)) or cite_f1 < args.min_cite_f1:
                    failures.append(
                        {"id": dataset_id, "reason": f"cite_f1 < {args.min_cite_f1}"}
                    )
            if args.min_instruction_acc is not None:
                if not isinstance(instruction_acc, (int, float)) or instruction_acc < args.min_instruction_acc:
                    failures.append(
                        {"id": dataset_id, "reason": f"instruction_acc < {args.min_instruction_acc}"}
                    )
            if args.min_state_integrity is not None:
                if not isinstance(state_integrity_rate, (int, float)) or state_integrity_rate < args.min_state_integrity:
                    failures.append(
                        {
                            "id": dataset_id,
                            "reason": f"state_integrity_rate < {args.min_state_integrity}",
                        }
                    )

        summary["thresholds"] = thresholds
        summary["failures"] = failures
        if failures:
            failure_counts: dict[str, int] = {}
            for failure in failures:
                dataset_id = failure.get("id")
                if dataset_id:
                    failure_counts[str(dataset_id)] = failure_counts.get(str(dataset_id), 0) + 1
            top = sorted(failure_counts.items(), key=lambda item: item[1], reverse=True)
            summary["top_failures"] = [
                {"id": dataset_id, "count": count} for dataset_id, count in top
            ]
        summary["status"] = "PASS" if not failures else "FAIL"

    out_path = Path(args.out) if args.out else runs_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_text = render_rag_benchmark_report(summary)
    report_path = Path(args.report) if args.report else runs_dir / "report.md"
    report_path.write_text(report_text, encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Wrote {report_path}")
    if failures:
        print("RAG benchmark failed thresholds.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
