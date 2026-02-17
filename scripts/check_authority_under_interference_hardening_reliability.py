from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check reliability across multiple authority_under_interference_hardening runs "
            "using hard-gate pass, holdout floors, and jitter limits."
        )
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        required=True,
        help="Run directories containing authority_under_interference_hardening_summary.json.",
    )
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--min-value-acc", type=float, default=0.92)
    parser.add_argument("--min-exact-acc", type=float, default=0.92)
    parser.add_argument("--min-cite-f1", type=float, default=0.88)
    parser.add_argument("--min-latest-support-hit-rate", type=float, default=0.92)
    parser.add_argument("--max-note-citation-rate", type=float, default=0.03)
    parser.add_argument("--max-stale-citation-rate", type=float, default=0.03)
    parser.add_argument("--max-authority-violation-rate", type=float, default=0.03)
    parser.add_argument("--max-value-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-exact-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-cite-f1-jitter", type=float, default=0.05)
    parser.add_argument("--max-authority-violation-jitter", type=float, default=0.05)
    parser.add_argument("--max-canary-exact-rate", type=float, default=0.85)
    parser.add_argument(
        "--allow-latest-nontarget",
        action="store_true",
        help=(
            "Compatibility no-op for generic family stage runners. "
            "Authority hardening reliability checks do not enforce stage-specific latest guards."
        ),
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def _read_summary(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _metric(summary: dict[str, Any], split: str, metric: str) -> float:
    sec = summary.get(split)
    if not isinstance(sec, dict):
        return float("nan")
    means = sec.get("means")
    if not isinstance(means, dict):
        return float("nan")
    value = means.get(metric)
    if isinstance(value, (int, float)):
        return float(value)
    return float("nan")


def _is_pass(summary: dict[str, Any], split: str) -> bool:
    sec = summary.get(split)
    return isinstance(sec, dict) and sec.get("status") == "PASS"


def _jitter(values: list[float]) -> float:
    finite = [v for v in values if v == v]
    if not finite:
        return float("nan")
    return max(finite) - min(finite)


def _canary_exact(summary: dict[str, Any]) -> float:
    raw = summary.get("canary_exact_rate")
    if isinstance(raw, (int, float)):
        return float(raw)
    return _metric(summary, "canary", "exact_acc")


def main() -> int:
    ns = _parse_args()
    run_dirs = [Path(p) for p in ns.run_dirs]
    if len(run_dirs) < ns.min_runs:
        print(f"Need at least {ns.min_runs} runs; got {len(run_dirs)}.")
        return 1

    summaries: list[tuple[Path, dict[str, Any]]] = []
    for run_dir in run_dirs:
        summary_path = run_dir / "authority_under_interference_hardening_summary.json"
        if not summary_path.exists():
            print(f"Missing summary file: {summary_path}")
            return 1
        summaries.append((run_dir, _read_summary(summary_path)))

    lines: list[str] = ["Authority-under-interference-hardening reliability check", f"Runs: {len(summaries)}"]
    failures: list[str] = []

    for run_dir, summary in summaries:
        top = summary.get("hard_gate_status")
        ok_top = top == "PASS"
        lines.append(f"[{'PASS' if ok_top else 'FAIL'}] {run_dir}: hard_gate_status={top}")
        if not ok_top:
            failures.append(f"{run_dir}: hard_gate_status != PASS")
        for split in ("anchors", "holdout"):
            ok_split = _is_pass(summary, split)
            lines.append(
                f"[{'PASS' if ok_split else 'FAIL'}] {run_dir}: {split}.status={summary.get(split, {}).get('status')}"
            )
            if not ok_split:
                failures.append(f"{run_dir}: {split}.status != PASS")

        canary_exact = _canary_exact(summary)
        canary_ok = (canary_exact == canary_exact) and (canary_exact <= ns.max_canary_exact_rate)
        lines.append(
            f"[{'PASS' if canary_ok else 'FAIL'}] {run_dir}: canary.exact_rate={canary_exact:.6f} <= {ns.max_canary_exact_rate:.6f}"
        )
        if not canary_ok:
            failures.append(f"{run_dir}: canary.exact_rate > {ns.max_canary_exact_rate}")

    floor_checks = [
        ("value_acc", ns.min_value_acc, ">="),
        ("exact_acc", ns.min_exact_acc, ">="),
        ("cite_f1", ns.min_cite_f1, ">="),
        ("latest_support_hit_rate", ns.min_latest_support_hit_rate, ">="),
        ("note_citation_rate", ns.max_note_citation_rate, "<="),
        ("stale_citation_rate", ns.max_stale_citation_rate, "<="),
        ("authority_violation_rate", ns.max_authority_violation_rate, "<="),
    ]
    for run_dir, summary in summaries:
        for metric, threshold, op in floor_checks:
            value = _metric(summary, "holdout", metric)
            if value != value:
                ok = False
            elif op == ">=":
                ok = value >= threshold
            else:
                ok = value <= threshold
            lines.append(
                f"[{'PASS' if ok else 'FAIL'}] {run_dir}: holdout.{metric}={value:.6f} {op} {threshold:.6f}"
            )
            if not ok:
                failures.append(f"{run_dir}: holdout.{metric} {op} {threshold}")

    value_acc_vals = [_metric(s, "holdout", "value_acc") for _, s in summaries]
    exact_acc_vals = [_metric(s, "holdout", "exact_acc") for _, s in summaries]
    cite_f1_vals = [_metric(s, "holdout", "cite_f1") for _, s in summaries]
    authority_violation_vals = [
        _metric(s, "holdout", "authority_violation_rate") for _, s in summaries
    ]
    canary_exact_vals = [_canary_exact(s) for _, s in summaries]
    jitter_checks = [
        ("holdout.value_acc_jitter", _jitter(value_acc_vals), ns.max_value_acc_jitter),
        ("holdout.exact_acc_jitter", _jitter(exact_acc_vals), ns.max_exact_acc_jitter),
        ("holdout.cite_f1_jitter", _jitter(cite_f1_vals), ns.max_cite_f1_jitter),
        (
            "holdout.authority_violation_jitter",
            _jitter(authority_violation_vals),
            ns.max_authority_violation_jitter,
        ),
        (
            "canary.exact_rate_jitter",
            _jitter(canary_exact_vals),
            ns.max_exact_acc_jitter,
        ),
    ]
    for name, value, max_allowed in jitter_checks:
        ok = (value == value) and (value <= max_allowed)
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}={value:.6f} <= {max_allowed:.6f}")
        if not ok:
            failures.append(f"{name} > {max_allowed}")

    status = "PASS" if not failures else "FAIL"
    lines.append(f"RESULT: {status}")
    print("\n".join(lines))

    payload = {
        "benchmark": "authority_under_interference_hardening_reliability",
        "runs": [str(r) for r in run_dirs],
        "status": status,
        "failures": failures,
        "jitter": {
            "holdout_value_acc": _jitter(value_acc_vals),
            "holdout_exact_acc": _jitter(exact_acc_vals),
            "holdout_cite_f1": _jitter(cite_f1_vals),
            "holdout_authority_violation_rate": _jitter(authority_violation_vals),
            "canary_exact_rate": _jitter(canary_exact_vals),
        },
        "max_canary_exact_rate": ns.max_canary_exact_rate,
    }
    if ns.out is not None:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {ns.out}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


