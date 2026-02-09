from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check reliability across multiple compression_families runs by enforcing "
            "hard-gate pass, threshold floors, and bounded metric jitter."
        )
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        required=True,
        help="Run directories that contain compression_families_summary.json.",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=2,
        help="Minimum number of runs required to evaluate reliability.",
    )
    parser.add_argument("--clb-min-precision", type=float, default=0.90)
    parser.add_argument("--clb-min-recall", type=float, default=0.90)
    parser.add_argument("--clb-max-bloat", type=float, default=0.20)
    parser.add_argument("--crv-min-value-acc", type=float, default=0.90)
    parser.add_argument("--crv-min-exact-acc", type=float, default=0.90)
    parser.add_argument("--crv-min-cite-f1", type=float, default=0.90)
    parser.add_argument(
        "--clb-max-precision-jitter",
        type=float,
        default=0.05,
        help="Max (max-min) across runs for CLB holdout precision.",
    )
    parser.add_argument(
        "--clb-max-recall-jitter",
        type=float,
        default=0.05,
        help="Max (max-min) across runs for CLB holdout recall.",
    )
    parser.add_argument(
        "--crv-max-value-acc-jitter",
        type=float,
        default=0.03,
        help="Max (max-min) across runs for CRV holdout value_acc.",
    )
    parser.add_argument(
        "--crv-max-exact-acc-jitter",
        type=float,
        default=0.03,
        help="Max (max-min) across runs for CRV holdout exact_acc.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write JSON summary.",
    )
    return parser.parse_args()


def _read_summary(path: Path) -> dict[str, Any]:
    # PowerShell Set-Content -Encoding UTF8 commonly writes a BOM on Windows.
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _metric(summary: dict[str, Any], family: str, split: str, metric: str) -> float:
    families = summary.get("families")
    if not isinstance(families, dict):
        return float("nan")
    fam = families.get(family)
    if not isinstance(fam, dict):
        return float("nan")
    sec = fam.get(split)
    if not isinstance(sec, dict):
        return float("nan")
    means = sec.get("means")
    if not isinstance(means, dict):
        return float("nan")
    value = means.get(metric)
    if isinstance(value, (int, float)):
        return float(value)
    return float("nan")


def _is_pass(summary: dict[str, Any], family: str, split: str) -> bool:
    families = summary.get("families")
    if not isinstance(families, dict):
        return False
    fam = families.get(family)
    if not isinstance(fam, dict):
        return False
    sec = fam.get(split)
    if not isinstance(sec, dict):
        return False
    return sec.get("status") == "PASS"


def _hard_pass(summary: dict[str, Any], family: str) -> bool:
    families = summary.get("families")
    if not isinstance(families, dict):
        return False
    fam = families.get(family)
    if not isinstance(fam, dict):
        return False
    return fam.get("hard_gate_status") == "PASS"


def _finite(values: list[float]) -> list[float]:
    return [v for v in values if v == v]  # NaN check


def _jitter(values: list[float]) -> float:
    fs = _finite(values)
    if not fs:
        return float("nan")
    return max(fs) - min(fs)


def main() -> int:
    args = _parse_args()
    run_dirs = [Path(p) for p in args.run_dirs]
    if len(run_dirs) < args.min_runs:
        print(f"Need at least {args.min_runs} runs; got {len(run_dirs)}.")
        return 1

    summaries: list[tuple[Path, dict[str, Any]]] = []
    for run_dir in run_dirs:
        path = run_dir / "compression_families_summary.json"
        if not path.exists():
            print(f"Missing summary file: {path}")
            return 1
        summaries.append((run_dir, _read_summary(path)))

    failures: list[str] = []
    lines: list[str] = []
    lines.append("Compression reliability check")
    lines.append(f"Runs: {len(summaries)}")

    for run_dir, summary in summaries:
        top = summary.get("hard_gate_status")
        ok_top = top == "PASS"
        lines.append(f"[{'PASS' if ok_top else 'FAIL'}] {run_dir}: hard_gate_status={top}")
        if not ok_top:
            failures.append(f"{run_dir}: hard_gate_status != PASS")

        for family in ("compression_loss_bounded", "compression_recoverability"):
            ok_fam = _hard_pass(summary, family)
            lines.append(
                f"[{'PASS' if ok_fam else 'FAIL'}] {run_dir}: {family}.hard_gate_status="
                f"{summary.get('families', {}).get(family, {}).get('hard_gate_status')}"
            )
            if not ok_fam:
                failures.append(f"{run_dir}: {family}.hard_gate_status != PASS")
            for split in ("anchors", "holdout"):
                ok_split = _is_pass(summary, family, split)
                lines.append(
                    f"[{'PASS' if ok_split else 'FAIL'}] {run_dir}: {family}.{split}.status="
                    f"{summary.get('families', {}).get(family, {}).get(split, {}).get('status')}"
                )
                if not ok_split:
                    failures.append(f"{run_dir}: {family}.{split}.status != PASS")

    for run_dir, summary in summaries:
        clb_precision = _metric(summary, "compression_loss_bounded", "holdout", "precision")
        clb_recall = _metric(summary, "compression_loss_bounded", "holdout", "recall")
        clb_bloat = _metric(summary, "compression_loss_bounded", "holdout", "bloat")
        crv_value_acc = _metric(summary, "compression_recoverability", "holdout", "value_acc")
        crv_exact_acc = _metric(summary, "compression_recoverability", "holdout", "exact_acc")
        crv_cite_f1 = _metric(summary, "compression_recoverability", "holdout", "cite_f1")

        checks = [
            ("clb.holdout.precision", clb_precision, ">=", args.clb_min_precision),
            ("clb.holdout.recall", clb_recall, ">=", args.clb_min_recall),
            ("clb.holdout.bloat", clb_bloat, "<=", args.clb_max_bloat),
            ("crv.holdout.value_acc", crv_value_acc, ">=", args.crv_min_value_acc),
            ("crv.holdout.exact_acc", crv_exact_acc, ">=", args.crv_min_exact_acc),
            ("crv.holdout.cite_f1", crv_cite_f1, ">=", args.crv_min_cite_f1),
        ]
        for name, value, op, threshold in checks:
            if value != value:
                ok = False
            elif op == ">=":
                ok = value >= threshold
            else:
                ok = value <= threshold
            lines.append(
                f"[{'PASS' if ok else 'FAIL'}] {run_dir}: {name}={value:.6f} {op} {threshold:.6f}"
            )
            if not ok:
                failures.append(f"{run_dir}: {name} {op} {threshold}")

    clb_precision_vals = [_metric(s, "compression_loss_bounded", "holdout", "precision") for _, s in summaries]
    clb_recall_vals = [_metric(s, "compression_loss_bounded", "holdout", "recall") for _, s in summaries]
    crv_value_vals = [_metric(s, "compression_recoverability", "holdout", "value_acc") for _, s in summaries]
    crv_exact_vals = [_metric(s, "compression_recoverability", "holdout", "exact_acc") for _, s in summaries]

    jitter_checks = [
        ("clb.holdout.precision_jitter", _jitter(clb_precision_vals), args.clb_max_precision_jitter),
        ("clb.holdout.recall_jitter", _jitter(clb_recall_vals), args.clb_max_recall_jitter),
        ("crv.holdout.value_acc_jitter", _jitter(crv_value_vals), args.crv_max_value_acc_jitter),
        ("crv.holdout.exact_acc_jitter", _jitter(crv_exact_vals), args.crv_max_exact_acc_jitter),
    ]
    for name, value, max_allowed in jitter_checks:
        ok = (value == value) and (value <= max_allowed)
        lines.append(
            f"[{'PASS' if ok else 'FAIL'}] {name}={value:.6f} <= {max_allowed:.6f}"
        )
        if not ok:
            failures.append(f"{name} > {max_allowed}")

    status = "PASS" if not failures else "FAIL"
    lines.append(f"RESULT: {status}")
    print("\n".join(lines))

    payload = {
        "benchmark": "compression_families_reliability",
        "runs": [str(d) for d in run_dirs],
        "status": status,
        "failures": failures,
        "jitter": {
            "clb_holdout_precision": _jitter(clb_precision_vals),
            "clb_holdout_recall": _jitter(clb_recall_vals),
            "crv_holdout_value_acc": _jitter(crv_value_vals),
            "crv_holdout_exact_acc": _jitter(crv_exact_vals),
        },
    }
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
