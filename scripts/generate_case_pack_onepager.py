from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _step(summary: dict[str, Any], name: str) -> dict[str, Any] | None:
    steps = summary.get("steps") or []
    for entry in steps:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def render_onepager(summary: dict[str, Any], run_dir: Path) -> str:
    lines: list[str] = []
    lines.append("# Case Pack Onepager")
    lines.append("")
    lines.append(f"Run dir: {run_dir}")
    model_id = summary.get("model_id")
    if model_id:
        lines.append(f"Model: {model_id}")
    lines.append(f"Generated: {summary.get('generated_at')}")
    lines.append(f"Status: {summary.get('status')}")
    lines.append("")
    lines.append("## Why this matters (3 signals)")
    lines.append("- Closed-book strict fails on domain packs -> shows grounding gap without retrieval.")
    lines.append("- Open-book improves cite_f1/value_acc -> shows retrieval + citations working.")
    lines.append("- Bad-actor demo fails holdout despite passing wall -> catches subtle safety regressions.")
    lines.append("")

    closed = _step(summary, "rag_closed_book_strict")
    open_book = _step(summary, "rag_open_book")
    if closed or open_book:
        lines.append("## RAG: closed-book vs open-book")
        if closed:
            lines.append(
                f"- Closed-book strict: {closed.get('status')} (value_acc {_fmt(closed.get('details', {}).get('value_acc'))}, "
                f"cite_f1 {_fmt(closed.get('details', {}).get('cite_f1'))})"
            )
        if open_book:
            details = open_book.get("details", {})
            lines.append(
                f"- Open-book: {open_book.get('status')} (value_acc {_fmt(details.get('value_acc'))}, "
                f"cite_f1 {_fmt(details.get('cite_f1'))}, retrieval_hit_rate {_fmt(details.get('retrieval_hit_rate'))})"
            )
            lines.append(
                f"- tokens_per_q {_fmt(details.get('tokens_per_q'), 1)}, wall_s_per_q {_fmt(details.get('wall_s_per_q'), 2)}"
            )
            source_pdf = details.get("source_pdf")
            if source_pdf:
                lines.append(f"- source_pdf {source_pdf}")
        lines.append("")

    reg_case = _step(summary, "regression_case")
    if reg_case:
        lines.append("## Internal tooling: regression case")
        lines.append(f"- status: {reg_case.get('status')}")
        lines.append(f"- pass gate: {Path(reg_case.get('run_dir', '')) / reg_case.get('details', {}).get('pass_gate', '')}")
        lines.append(f"- fail gate: {Path(reg_case.get('run_dir', '')) / reg_case.get('details', {}).get('fail_gate', '')}")
        lines.append("")

    bad_actor = _step(summary, "bad_actor_demo")
    if bad_actor:
        lines.append("## Compliance/safety: bad-actor demo")
        status = bad_actor.get("status")
        details = bad_actor.get("details", {})
        if details.get("expected_fail"):
            if details.get("expected_fail_observed"):
                status = "PASS (expected holdout FAIL)"
            else:
                status = "FAIL (expected holdout FAIL)"
        lines.append(f"- status: {status}")
        lines.append(f"- holdout gate: {Path(bad_actor.get('run_dir', '')) / bad_actor.get('details', {}).get('holdout_gate', '')}")
        wall_summary = bad_actor.get("details", {}).get("wall_summary", "")
        if isinstance(wall_summary, str):
            wall_summary = wall_summary.replace("\\\\", "\\")
        lines.append(f"- wall summary: {wall_summary}")
        if details.get("expected_fail"):
            lines.append("- note: holdout failure is expected; catching it is the success signal.")
        lines.append("")

    lines.append("## How to use this")
    lines.append("- If closed-book strict passes, your model likely memorized or already knows the domain.")
    lines.append("- If open-book improves cite_f1/value_acc, retrieval is working and citations are grounded.")
    lines.append("- If bad-actor fails holdout, your safety gate is catching subtle regressions.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a case pack onepager.")
    parser.add_argument("--run-dir", required=True, help="Case pack run directory.")
    parser.add_argument("--out", default="", help="Output markdown path (default: case_pack_onepager.md in run dir).")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    summary_path = run_dir / "case_pack_summary.json"
    if not summary_path.exists():
        raise SystemExit(f"Missing summary: {summary_path}")
    summary = _load_json(summary_path)
    content = render_onepager(summary, run_dir)
    out_path = Path(args.out) if args.out else run_dir / "case_pack_onepager.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
