import argparse
import json
import os
from datetime import datetime
from pathlib import Path

DATASETS = [
    ("kv_commentary", "KV commentary"),
    ("kv_commentary_large", "KV commentary (large)"),
    ("goldevidencebench", "GoldEvidenceBench"),
]


def _load_summary(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        results = payload
    else:
        results = None
        for key in ("results", "datasets", "summary", "runs"):
            val = payload.get(key)
            if isinstance(val, list):
                results = val
                break
        if results is None:
            results = next((v for v in payload.values() if isinstance(v, list)), [])
    return {row.get("id"): row for row in results if isinstance(row, dict) and row.get("id")}


def _load_results(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list) and payload:
        entry = payload[0]
        return entry.get("metrics", entry)
    if isinstance(payload, dict):
        return payload.get("metrics", payload)
    return {}


def _fmt(value: object) -> str:
    if value is None:
        return "na"
    try:
        return f"{float(value):.3f}"
    except Exception:
        return str(value)


def _has_block(lines: list[str], run_dir: str, base_dir: str) -> bool:
    run_line = f"run_dir: {run_dir}"
    base_line = f"base_dir: {base_dir}"
    for idx, line in enumerate(lines):
        if line.strip() == run_line and idx + 1 < len(lines) and lines[idx + 1].strip() == base_line:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Append a before/after accuracy summary to docs/RUN_LOG.md."
    )
    parser.add_argument(
        "--base-dir",
        default=os.getenv("RUN_BASE"),
        help="Base run dir (contains summary.json). Can also set RUN_BASE.",
    )
    parser.add_argument(
        "--run-dir",
        default=os.getenv("RUN_NEW"),
        help="New run dir (contains results_*.json). Can also set RUN_NEW.",
    )
    parser.add_argument(
        "--log-path",
        default="docs/RUN_LOG.md",
        help="Run log path (default: docs/RUN_LOG.md).",
    )
    parser.add_argument(
        "--stamp",
        default=None,
        help="Optional timestamp label (default: current local time).",
    )
    parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="Append even if an identical run/base block already exists.",
    )
    args = parser.parse_args()

    if not args.base_dir or not args.run_dir:
        raise SystemExit("Set --base-dir and --run-dir (or RUN_BASE/RUN_NEW).")

    base = Path(args.base_dir)
    run = Path(args.run_dir)
    log_path = Path(args.log_path)

    summary_path = base / "summary.json"
    if not summary_path.exists():
        raise SystemExit(f"Missing summary.json: {summary_path}")

    before = _load_summary(summary_path)

    lines = []
    for dataset_id, label in DATASETS:
        b = before.get(dataset_id, {})
        a = _load_results(run / f"results_{dataset_id}.json")
        lines.append(
            f"| {label} | {_fmt(b.get('value_acc'))} | {_fmt(a.get('value_acc'))} | "
            f"{_fmt(b.get('exact_acc'))} | {_fmt(a.get('exact_acc'))} | "
            f"{_fmt(b.get('entailment'))} | {_fmt(a.get('entailment'))} | "
            f"{_fmt(b.get('cite_f1'))} | {_fmt(a.get('cite_f1'))} |"
        )

    stamp = args.stamp or datetime.now().strftime("%Y-%m-%d %H:%M")
    block = (
        f"\n## {stamp} accuracy-first rerun\n"
        f"run_dir: {run}\n"
        f"base_dir: {base}\n\n"
        "| dataset | value_acc (before) | value_acc (after) | exact_acc (before) | exact_acc (after) | "
        "entailment (before) | entailment (after) | cite_f1 (before) | cite_f1 (after) |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(lines)
        + "\n"
    )

    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
    else:
        content = ""

    if not args.allow_duplicate and content:
        if _has_block(content.splitlines(), str(run), str(base)):
            print(f"Skipped: block already exists for run_dir/base_dir in {log_path}")
            return 0

    log_path.write_text(content + block, encoding="utf-8")
    print(f"Appended summary to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
