from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REASON_RULES = {
    "prefer_main_scope": "Allow non-main scope when instruction or allow_overlay implies a modal/drawer.",
    "avoid_overlay": "If overlay/modal is requested or allowed, do not filter overlay candidates.",
    "prefer_enabled": "Keep prefer-enabled as default; only override when instruction mentions disabled targets.",
    "prefer_visible": "Keep prefer-visible as default; only override when instruction mentions hidden targets.",
    "prefer_clickable": "Keep prefer-clickable as default; add an explicit override if instructions mention non-clickable.",
    "prefer_primary_id": "Add a rule to prioritize primary labels/ids only when instruction requests primary.",
    "label_mismatch": "Add label keyword cues to disambiguate and avoid over-reliance on geometry.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _append_count(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a UI SA distillation report from local-optimum variant runs."
    )
    parser.add_argument(
        "--variants-dir",
        required=True,
        help="Directory containing summary.json from run_ui_local_optimum_variants.ps1",
    )
    parser.add_argument(
        "--holdout-name",
        default="",
        help="Variant name to exclude from distillation (holdout).",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional output path for distillation_report.json.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print a one-line status summary instead of the full JSON report.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Force printing the full JSON report even when --out is set.",
    )
    args = parser.parse_args()

    variants_dir = Path(args.variants_dir)
    summary_path = variants_dir / "summary.json"
    if not summary_path.exists():
        print(f"summary.json not found: {summary_path}")
        return 1

    summary = _load_json(summary_path)
    holdout_name = args.holdout_name or summary.get("holdout_name") or ""

    variants = summary.get("variants", [])
    if not isinstance(variants, list):
        print("summary.json variants must be a list.")
        return 1

    included_variants: list[str] = []
    skipped_variants: list[str] = []
    decoy_reason_counts: dict[str, int] = {}
    feature_diff_counts: dict[str, int] = {}
    step_signature_counts: dict[str, int] = {}
    sample_diffs: list[dict[str, Any]] = []
    total_seed_runs = 0
    sa_wins = 0

    accept_rates: list[float] = []
    runtime_ms_per_iter: list[float] = []
    move_accept_rates: dict[str, list[float]] = {"swap": [], "replace": [], "rebuild": []}
    variant_breakdown: dict[str, Any] = {}
    policy_task_pass_rates: list[float] = []
    greedy_task_pass_rates: list[float] = []
    sa_task_pass_rates: list[float] = []

    for variant in variants:
        if not isinstance(variant, dict):
            continue
        name = variant.get("name")
        out_path = variant.get("out")
        if not isinstance(name, str) or not isinstance(out_path, str):
            continue
        out_file = variants_dir / Path(out_path).name
        if not out_file.exists():
            out_file = Path(out_path)
        if not out_file.exists():
            print(f"Missing variant output: {out_path}")
            continue

        data = _load_json(out_file)
        seed_runs = data.get("seed_runs", [])
        if not isinstance(seed_runs, list):
            continue

        variant_seed_runs = len(seed_runs)
        variant_sa_wins = 0
        variant_decoy_reasons: dict[str, int] = {}
        variant_feature_diffs: dict[str, int] = {}
        variant_step_signatures: dict[str, int] = {}
        variant_accept_rates: list[float] = []
        variant_runtime_ms_per_iter: list[float] = []
        variant_move_accept_rates: dict[str, list[float]] = {
            "swap": [],
            "replace": [],
            "rebuild": [],
        }
        variant_policy_task_pass_rates: list[float] = []
        variant_greedy_task_pass_rates: list[float] = []
        variant_sa_task_pass_rates: list[float] = []

        for run in seed_runs:
            if not isinstance(run, dict):
                continue
            if run.get("sa_beats_greedy"):
                variant_sa_wins += 1
                diff = run.get("sa_diff")
                if isinstance(diff, dict):
                    reasons = diff.get("decoy_reasons", [])
                    if isinstance(reasons, list):
                        for reason in reasons:
                            if isinstance(reason, str) and reason:
                                _append_count(variant_decoy_reasons, reason)
                    feature_diff = diff.get("feature_diff", {})
                    if isinstance(feature_diff, dict):
                        for key in feature_diff.keys():
                            if isinstance(key, str):
                                _append_count(variant_feature_diffs, key)
                    row_id = diff.get("row_id")
                    step_number = diff.get("step_number")
                    if isinstance(row_id, str) and step_number is not None:
                        signature = f"{row_id}:{step_number}"
                        _append_count(variant_step_signatures, signature)
                    if len(sample_diffs) < 5:
                        sample_diffs.append(
                            {
                                "variant": name,
                                "row_id": diff.get("row_id"),
                                "step_number": diff.get("step_number"),
                                "decoy_reasons": diff.get("decoy_reasons", []),
                                "feature_diff_keys": list(feature_diff.keys())
                                if isinstance(feature_diff, dict)
                                else [],
                            }
                        )

            sa_block = run.get("sa", {})
            if isinstance(sa_block, dict):
                telemetry = sa_block.get("telemetry", {})
                if isinstance(telemetry, dict):
                    accept_rate = telemetry.get("accept_rate")
                    if isinstance(accept_rate, (int, float)):
                        variant_accept_rates.append(float(accept_rate))
                    runtime = telemetry.get("runtime_ms_per_iter")
                    if isinstance(runtime, (int, float)):
                        variant_runtime_ms_per_iter.append(float(runtime))
                    move_stats = telemetry.get("move_stats", {})
                    if isinstance(move_stats, dict):
                        for move, stats in move_stats.items():
                            if move not in variant_move_accept_rates or not isinstance(stats, dict):
                                continue
                            rate = stats.get("accept_rate")
                            if isinstance(rate, (int, float)):
                                variant_move_accept_rates[move].append(float(rate))

            policy_block = run.get("policy", {})
            if isinstance(policy_block, dict):
                sequence_metrics = policy_block.get("sequence_metrics", {})
                if isinstance(sequence_metrics, dict):
                    task_pass_rate = sequence_metrics.get("task_pass_rate")
                    if isinstance(task_pass_rate, (int, float)):
                        variant_policy_task_pass_rates.append(float(task_pass_rate))

            greedy_block = run.get("greedy", {})
            if isinstance(greedy_block, dict):
                sequence_metrics = greedy_block.get("sequence_metrics", {})
                if isinstance(sequence_metrics, dict):
                    task_pass_rate = sequence_metrics.get("task_pass_rate")
                    if isinstance(task_pass_rate, (int, float)):
                        variant_greedy_task_pass_rates.append(float(task_pass_rate))

            if isinstance(sa_block, dict):
                sequence_metrics = sa_block.get("sequence_metrics", {})
                if isinstance(sequence_metrics, dict):
                    task_pass_rate = sequence_metrics.get("task_pass_rate")
                    if isinstance(task_pass_rate, (int, float)):
                        variant_sa_task_pass_rates.append(float(task_pass_rate))

        variant_breakdown[name] = {
            "seeds": variant_seed_runs,
            "sa_wins": variant_sa_wins,
            "sa_beats_greedy_rate": (
                variant_sa_wins / variant_seed_runs if variant_seed_runs else 0.0
            ),
            "policy_task_pass_rate_mean": _mean(variant_policy_task_pass_rates),
            "policy_task_pass_rate_min": (
                min(variant_policy_task_pass_rates) if variant_policy_task_pass_rates else 0.0
            ),
            "greedy_task_pass_rate_mean": _mean(variant_greedy_task_pass_rates),
            "greedy_task_pass_rate_min": (
                min(variant_greedy_task_pass_rates) if variant_greedy_task_pass_rates else 0.0
            ),
            "sa_task_pass_rate_mean": _mean(variant_sa_task_pass_rates),
            "sa_task_pass_rate_min": (
                min(variant_sa_task_pass_rates) if variant_sa_task_pass_rates else 0.0
            ),
            "decoy_reason_counts": variant_decoy_reasons,
            "feature_diff_counts": variant_feature_diffs,
            "step_signature_counts": variant_step_signatures,
            "telemetry_summary": {
                "accept_rate_mean": _mean(variant_accept_rates),
                "runtime_ms_per_iter_mean": _mean(variant_runtime_ms_per_iter),
                "move_accept_rate_mean": {
                    move: _mean(values)
                    for move, values in variant_move_accept_rates.items()
                },
            },
            "excluded_from_distillation": bool(holdout_name and name == holdout_name),
        }

        if holdout_name and name == holdout_name:
            skipped_variants.append(name)
            continue

        included_variants.append(name)
        total_seed_runs += variant_seed_runs
        sa_wins += variant_sa_wins

        for reason, count in variant_decoy_reasons.items():
            decoy_reason_counts[reason] = decoy_reason_counts.get(reason, 0) + count
        for key, count in variant_feature_diffs.items():
            feature_diff_counts[key] = feature_diff_counts.get(key, 0) + count
        for signature, count in variant_step_signatures.items():
            step_signature_counts[signature] = step_signature_counts.get(signature, 0) + count

        for value in variant_accept_rates:
            accept_rates.append(value)
        for value in variant_runtime_ms_per_iter:
            runtime_ms_per_iter.append(value)
        for move, values in variant_move_accept_rates.items():
            move_accept_rates[move].extend(values)
        policy_task_pass_rates.extend(variant_policy_task_pass_rates)
        greedy_task_pass_rates.extend(variant_greedy_task_pass_rates)
        sa_task_pass_rates.extend(variant_sa_task_pass_rates)

    rule_backlog = []
    for reason, count in sorted(decoy_reason_counts.items(), key=lambda item: item[1], reverse=True):
        rule_backlog.append(
            {
                "reason": reason,
                "count": count,
                "suggested_rule": REASON_RULES.get(reason, "Review diff and add a targeted rule."),
            }
        )

    report = {
        "variants_dir": str(variants_dir),
        "holdout_name": holdout_name,
        "included_variants": included_variants,
        "skipped_variants": skipped_variants,
        "variant_breakdown": variant_breakdown,
        "total_seed_runs": total_seed_runs,
        "sa_wins": sa_wins,
        "sa_beats_greedy_rate": sa_wins / total_seed_runs if total_seed_runs else 0.0,
        "policy_task_pass_rate_mean": _mean(policy_task_pass_rates),
        "greedy_task_pass_rate_mean": _mean(greedy_task_pass_rates),
        "sa_task_pass_rate_mean": _mean(sa_task_pass_rates),
        "decoy_reason_counts": decoy_reason_counts,
        "feature_diff_counts": feature_diff_counts,
        "step_signature_counts": step_signature_counts,
        "telemetry_summary": {
            "accept_rate_mean": _mean(accept_rates),
            "runtime_ms_per_iter_mean": _mean(runtime_ms_per_iter),
            "move_accept_rate_mean": {
                move: _mean(values) for move, values in move_accept_rates.items()
            },
        },
        "rule_backlog": rule_backlog,
        "sample_diffs": sample_diffs,
    }

    non_holdout_policy = [
        variant_breakdown[name]["policy_task_pass_rate_min"]
        for name in included_variants
        if name in variant_breakdown
        and isinstance(variant_breakdown[name].get("policy_task_pass_rate_min"), (int, float))
    ]
    non_holdout_greedy = [
        variant_breakdown[name]["greedy_task_pass_rate_min"]
        for name in included_variants
        if name in variant_breakdown
        and isinstance(variant_breakdown[name].get("greedy_task_pass_rate_min"), (int, float))
    ]
    non_holdout_sa = [
        variant_breakdown[name]["sa_task_pass_rate_min"]
        for name in included_variants
        if name in variant_breakdown
        and isinstance(variant_breakdown[name].get("sa_task_pass_rate_min"), (int, float))
    ]
    report["non_holdout"] = {
        "variants": included_variants,
        "policy_task_pass_rate_min": min(non_holdout_policy) if non_holdout_policy else 0.0,
        "greedy_task_pass_rate_min": min(non_holdout_greedy) if non_holdout_greedy else 0.0,
        "sa_task_pass_rate_min": min(non_holdout_sa) if non_holdout_sa else 0.0,
    }
    holdout_summary: dict[str, Any] = {"name": holdout_name}
    if holdout_name and holdout_name in variant_breakdown:
        holdout_variant = variant_breakdown[holdout_name]
        holdout_summary.update(
            {
                "policy_task_pass_rate_mean": holdout_variant.get(
                    "policy_task_pass_rate_mean", 0.0
                ),
                "policy_task_pass_rate_min": holdout_variant.get(
                    "policy_task_pass_rate_min", 0.0
                ),
                "greedy_task_pass_rate_mean": holdout_variant.get(
                    "greedy_task_pass_rate_mean", 0.0
                ),
                "greedy_task_pass_rate_min": holdout_variant.get(
                    "greedy_task_pass_rate_min", 0.0
                ),
                "sa_task_pass_rate_mean": holdout_variant.get("sa_task_pass_rate_mean", 0.0),
                "sa_task_pass_rate_min": holdout_variant.get("sa_task_pass_rate_min", 0.0),
                "sa_beats_greedy_rate": holdout_variant.get("sa_beats_greedy_rate", 0.0),
            }
        )
    report["holdout"] = holdout_summary

    out_path = Path(args.out) if args.out else variants_dir / "distillation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_json = args.print_json or (not args.quiet and not args.out)
    if not print_json:
        print(
            "ui_sa_distillation_report: "
            f"included={len(included_variants)} "
            f"skipped={len(skipped_variants)} "
            f"sa_beats_greedy_rate={report.get('sa_beats_greedy_rate', 0.0):.3f} "
            f"out={out_path}"
        )
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
