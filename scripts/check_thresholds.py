from __future__ import annotations

import argparse
import json
from pathlib import Path

from goldevidencebench.thresholds import evaluate_checks, format_issues, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Check use-case thresholds from summary.json files.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/usecase_checks.json"),
        help="Path to threshold config JSON.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root for summary_path entries (default: repo root).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional JSON output path for issues and error count.",
    )
    parser.add_argument(
        "--quiet-passes",
        action="store_true",
        help="Hide PASS lines in console output (show FAIL/MISSING/SKIP only).",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    issues, error_count = evaluate_checks(config, root=args.root)
    issues_to_print = issues
    if args.quiet_passes:
        issues_to_print = [issue for issue in issues if issue.status != "pass"]
    print(format_issues(issues_to_print))
    if args.quiet_passes and not issues_to_print:
        print("All checks passed.")
    if args.out:
        payload = {
            "issues": [issue.__dict__ for issue in issues],
            "error_count": error_count,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
