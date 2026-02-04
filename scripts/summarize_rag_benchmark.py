from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from goldevidencebench import schema_validation
from goldevidencebench.rag_benchmark import (
    render_rag_benchmark_report,
    summarize_rag_benchmark,
)


def _write_compact_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
    parser.add_argument("--min-exact-acc", type=float, help="Fail if exact_acc < min.")
    parser.add_argument("--min-entailment", type=float, help="Fail if entailment < min.")
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
    parser.add_argument(
        "--min-answer-correct-given-selected",
        type=float,
        help="Fail if answer_correct_given_selected < min.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    runs_dir = Path(args.runs_dir)
    summary = summarize_rag_benchmark(config_path, runs_dir)

    thresholds = {}
    if args.min_value_acc is not None:
        thresholds["value_acc"] = args.min_value_acc
    if args.min_exact_acc is not None:
        thresholds["exact_acc"] = args.min_exact_acc
    if args.min_entailment is not None:
        thresholds["entailment"] = args.min_entailment
    if args.min_answer_correct_given_selected is not None:
        thresholds["answer_correct_given_selected"] = args.min_answer_correct_given_selected
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
            exact_acc = entry.get("exact_acc")
            entailment = entry.get("entailment")
            answer_correct = entry.get("answer_correct_given_selected")
            cite_f1 = entry.get("cite_f1")
            instruction_acc = entry.get("instruction_acc")
            state_integrity_rate = entry.get("state_integrity_rate")
            if args.min_value_acc is not None:
                if not isinstance(value_acc, (int, float)) or value_acc < args.min_value_acc:
                    failures.append(
                        {"id": dataset_id, "reason": f"value_acc < {args.min_value_acc}"}
                    )
            if args.min_exact_acc is not None:
                if not isinstance(exact_acc, (int, float)) or exact_acc < args.min_exact_acc:
                    failures.append(
                        {"id": dataset_id, "reason": f"exact_acc < {args.min_exact_acc}"}
                    )
            if args.min_entailment is not None:
                if not isinstance(entailment, (int, float)) or entailment < args.min_entailment:
                    failures.append(
                        {"id": dataset_id, "reason": f"entailment < {args.min_entailment}"}
                    )
            if args.min_answer_correct_given_selected is not None:
                if not isinstance(answer_correct, (int, float)) or answer_correct < args.min_answer_correct_given_selected:
                    failures.append(
                        {
                            "id": dataset_id,
                            "reason": f"answer_correct_given_selected < {args.min_answer_correct_given_selected}",
                        }
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

    schema_validation.validate_or_raise(
        summary,
        schema_validation.schema_path("rag_benchmark_summary.schema.json"),
    )
    out_path = Path(args.out) if args.out else runs_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_text = render_rag_benchmark_report(summary)
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
                "value_acc": entry.get("value_acc"),
                "exact_acc": entry.get("exact_acc"),
                "entailment": entry.get("entailment"),
                "answer_correct_given_selected": entry.get("answer_correct_given_selected"),
                "cite_f1": entry.get("cite_f1"),
                "retrieval_hit_rate": entry.get("retrieval_hit_rate"),
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
        "datasets": compact_rows,
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
            "value_acc",
            "exact_acc",
            "entailment",
            "answer_correct_given_selected",
            "cite_f1",
            "retrieval_hit_rate",
            "status",
        ],
    )

    print(f"Wrote {out_path}")
    print(f"Wrote {report_path}")
    if failures:
        print("RAG benchmark failed thresholds.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
