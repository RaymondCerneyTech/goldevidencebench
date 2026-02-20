from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-trap capability check report from capability snapshots."
        )
    )
    parser.add_argument(
        "--jobs-config",
        type=Path,
        default=Path("configs/capability_check_jobs.json"),
        help="Capability check jobs config JSON.",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("runs"),
        help="Runs root containing latest capability snapshot pointers.",
    )
    parser.add_argument(
        "--snapshot-archive-dir",
        type=Path,
        default=Path("runs/capability_snapshots"),
        help="Archive directory with capability snapshots.",
    )
    parser.add_argument(
        "--after-snapshot",
        type=Path,
        default=Path("runs/capability_snapshot_latest.json"),
        help="Current snapshot path.",
    )
    parser.add_argument(
        "--before-snapshot",
        type=Path,
        default=None,
        help="Baseline snapshot path (defaults to most recent previous archive snapshot).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/capability_check_latest.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("runs/capability_check_latest.md"),
        help="Output markdown path.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _select_previous_snapshot(
    after_snapshot: Path,
    after_snapshot_payload: dict[str, Any],
    archive_dir: Path,
) -> Path | None:
    if not archive_dir.exists():
        return None
    candidates = sorted(
        [p for p in archive_dir.glob("capability_snapshot_*.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    after_resolved = after_snapshot.resolve()
    after_generated = after_snapshot_payload.get("generated_at_utc")
    for candidate in candidates:
        if candidate.resolve() == after_resolved:
            continue
        try:
            candidate_payload = _read_json(candidate)
        except Exception:
            continue
        if (
            isinstance(after_generated, str)
            and isinstance(candidate_payload.get("generated_at_utc"), str)
            and candidate_payload.get("generated_at_utc") == after_generated
        ):
            # Skip the archive copy written for the same current snapshot.
            continue
        return candidate
    return None


def _build_metric_map(snapshot: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["snapshot.status"] = snapshot.get("status")

    failure_reasons = snapshot.get("failure_reasons")
    if isinstance(failure_reasons, list):
        out["snapshot.failure_count"] = len(failure_reasons)
    warning_reasons = snapshot.get("warning_reasons")
    if isinstance(warning_reasons, list):
        out["snapshot.warning_count"] = len(warning_reasons)

    metrics = snapshot.get("metrics")
    if isinstance(metrics, dict):
        for key, value in metrics.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[f"metrics.{key}"] = value

    sources = snapshot.get("sources")
    if isinstance(sources, dict):
        for source_name, info in sources.items():
            if not isinstance(info, dict):
                continue
            status = info.get("status")
            present = info.get("present")
            if isinstance(status, str):
                out[f"source.{source_name}.status"] = status
                out[f"source.{source_name}.status_is_pass"] = status == "PASS"
            if isinstance(present, bool):
                out[f"source.{source_name}.present"] = present
    return out


@dataclass
class RuleEval:
    path: str
    op: str
    expected: Any
    actual: Any
    weight: float
    critical: bool
    passed: bool
    missing: bool
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "op": self.op,
            "expected": self.expected,
            "actual": self.actual,
            "weight": self.weight,
            "critical": self.critical,
            "passed": self.passed,
            "missing": self.missing,
            "reason": self.reason,
        }


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _compare(actual: Any, op: str, expected: Any) -> tuple[bool, str | None]:
    if op in {"ge", "gt", "le", "lt"}:
        left = _to_float(actual)
        right = _to_float(expected)
        if left is None or right is None:
            return False, "non_numeric"
        if op == "ge":
            return left >= right, None
        if op == "gt":
            return left > right, None
        if op == "le":
            return left <= right, None
        return left < right, None

    if op == "eq":
        return actual == expected, None
    if op == "ne":
        return actual != expected, None
    return False, f"unsupported_op:{op}"


def _evaluate_job(job: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    rules = job.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"Job '{job.get('id')}' must contain non-empty rules.")

    evaluated: list[RuleEval] = []
    total_weight = 0.0
    passed_weight = 0.0
    critical_total = 0.0
    critical_failed = 0.0

    for rule in rules:
        path = str(rule.get("path") or "").strip()
        op = str(rule.get("op") or "").strip().lower()
        expected = rule.get("value")
        weight = float(rule.get("weight", 1.0))
        critical = bool(rule.get("critical", False))
        actual = metrics.get(path)
        missing = path not in metrics
        if missing:
            passed = False
            reason = "missing_path"
        else:
            passed, reason = _compare(actual, op, expected)
        entry = RuleEval(
            path=path,
            op=op,
            expected=expected,
            actual=actual,
            weight=weight,
            critical=critical,
            passed=passed,
            missing=missing,
            reason=reason,
        )
        evaluated.append(entry)
        total_weight += weight
        if passed:
            passed_weight += weight
        if critical:
            critical_total += weight
            if not passed:
                critical_failed += weight

    pass_threshold = float(job.get("pass_threshold", 1.0))
    success_rate = (passed_weight / total_weight) if total_weight > 0 else 0.0
    critical_fail_rate = (critical_failed / critical_total) if critical_total > 0 else 0.0
    status = "PASS" if success_rate >= pass_threshold else "FAIL"
    return {
        "status": status,
        "pass_threshold": pass_threshold,
        "success_rate": success_rate,
        "critical_fail_rate": critical_fail_rate,
        "rules": [r.as_dict() for r in evaluated],
    }


def _classify_job(
    before_eval: dict[str, Any],
    after_eval: dict[str, Any],
    policy: dict[str, Any],
) -> str:
    unlock = policy.get("unlock", {})
    harden = policy.get("harden", {})
    regress = policy.get("regress", {})

    before_success = float(before_eval["success_rate"])
    after_success = float(after_eval["success_rate"])
    after_critical_fail_rate = float(after_eval["critical_fail_rate"])

    unlock_before_max = float(unlock.get("before_max_success", 0.6))
    unlock_after_min = float(unlock.get("after_min_success", 0.9))
    unlock_max_critical = float(unlock.get("max_after_critical_fail_rate", 0.02))
    if (
        before_success < unlock_before_max
        and after_success >= unlock_after_min
        and after_critical_fail_rate <= unlock_max_critical
    ):
        return "Unlocked"

    harden_before_min = float(harden.get("before_min_success", 0.9))
    harden_after_min = float(harden.get("after_min_success", 0.95))
    harden_min_delta = float(harden.get("min_delta", 0.03))
    harden_max_critical = float(harden.get("max_after_critical_fail_rate", 0.02))
    if (
        before_success >= harden_before_min
        and after_success >= harden_after_min
        and (after_success - before_success) >= harden_min_delta
        and after_critical_fail_rate <= harden_max_critical
    ):
        return "Hardened"

    regress_epsilon = float(regress.get("epsilon", 0.02))
    if after_success + regress_epsilon < before_success:
        return "Regressed"

    return "Unchanged"


def _build_markdown(payload: dict[str, Any]) -> str:
    def _fmt_metric(value: Any) -> str:
        if value is None:
            return "n/a"
        try:
            return f"{float(value):.3f}"
        except (TypeError, ValueError):
            return str(value)

    lines: list[str] = []
    lines.append("# Capability Check Report")
    lines.append("")
    lines.append(f"- generated_at: `{payload['generated_at_utc']}`")
    lines.append(f"- status: `{payload['status']}`")
    lines.append(f"- after_snapshot: `{payload['after_snapshot']}`")
    lines.append(f"- before_snapshot: `{payload.get('before_snapshot')}`")
    lines.append(f"- utility_delta: `{payload['summary'].get('utility_delta')}`")
    lines.append("")
    lines.append("| Job | Before | After | Delta | Class |")
    lines.append("|---|---:|---:|---:|---|")
    for row in payload.get("jobs", []):
        before_rate = row.get("before", {}).get("success_rate")
        after_rate = row.get("after", {}).get("success_rate")
        delta = row.get("delta_success_rate")
        classification = row.get("classification")
        lines.append(
            f"| `{row.get('id')}` | {_fmt_metric(before_rate)} | {_fmt_metric(after_rate)} | {_fmt_metric(delta)} | {classification} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ns = _parse_args()
    jobs_config = _read_json(ns.jobs_config)
    jobs = jobs_config.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("Capability check jobs config must include non-empty jobs[] list.")

    if not ns.after_snapshot.exists():
        raise FileNotFoundError(f"After snapshot not found: {ns.after_snapshot}")
    after_snapshot = _read_json(ns.after_snapshot)
    after_metrics = _build_metric_map(after_snapshot)

    before_snapshot_path = ns.before_snapshot
    if before_snapshot_path is None:
        before_snapshot_path = _select_previous_snapshot(
            after_snapshot=ns.after_snapshot,
            after_snapshot_payload=after_snapshot,
            archive_dir=ns.snapshot_archive_dir,
        )

    has_before = before_snapshot_path is not None and before_snapshot_path.exists()
    before_snapshot: dict[str, Any] | None = None
    before_metrics: dict[str, Any] = {}
    if has_before:
        before_snapshot = _read_json(before_snapshot_path)
        before_metrics = _build_metric_map(before_snapshot)

    policy = jobs_config.get("policy", {})
    risk_penalty_lambda = float(policy.get("risk_penalty_lambda", 1.0))

    job_rows: list[dict[str, Any]] = []
    utility_delta_total = 0.0
    counts = {"Unlocked": 0, "Hardened": 0, "Unchanged": 0, "Regressed": 0, "NoBaseline": 0}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            raise ValueError("Each capability check job must define id.")
        name = str(job.get("name") or job_id)
        value_weight = float(job.get("value_weight", 1.0))

        after_eval = _evaluate_job(job, after_metrics)
        before_eval = _evaluate_job(job, before_metrics) if has_before else {
            "status": "N/A",
            "pass_threshold": float(job.get("pass_threshold", 1.0)),
            "success_rate": 0.0,
            "critical_fail_rate": 0.0,
            "rules": [],
        }

        if has_before:
            classification = _classify_job(before_eval, after_eval, policy)
            delta_success_rate = float(after_eval["success_rate"]) - float(before_eval["success_rate"])
            utility_contribution = (value_weight * delta_success_rate) - (
                risk_penalty_lambda * float(after_eval["critical_fail_rate"])
            )
            utility_delta_total += utility_contribution
        else:
            classification = "NoBaseline"
            delta_success_rate = None
            utility_contribution = None

        counts[classification] += 1
        job_rows.append(
            {
                "id": job_id,
                "name": name,
                "value_weight": value_weight,
                "classification": classification,
                "before": before_eval,
                "after": after_eval,
                "delta_success_rate": delta_success_rate,
                "utility_contribution": utility_contribution,
            }
        )

    if has_before:
        status = "FAIL" if counts["Regressed"] > 0 else "PASS"
    else:
        status = "NO_BASELINE"

    payload = {
        "benchmark": "capability_check_report",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "inputs": {
            "jobs_config": str(ns.jobs_config),
            "after_snapshot": str(ns.after_snapshot),
            "before_snapshot": str(before_snapshot_path) if before_snapshot_path is not None else None,
        },
        "policy": {
            "unlock": policy.get("unlock", {}),
            "harden": policy.get("harden", {}),
            "regress": policy.get("regress", {}),
            "risk_penalty_lambda": risk_penalty_lambda,
        },
        "after_snapshot": str(ns.after_snapshot),
        "before_snapshot": str(before_snapshot_path) if before_snapshot_path is not None else None,
        "jobs": job_rows,
        "summary": {
            "has_before_snapshot": has_before,
            "job_count": len(job_rows),
            "classification_counts": counts,
            "utility_delta": utility_delta_total if has_before else None,
            "unlocked_jobs": [row["id"] for row in job_rows if row["classification"] == "Unlocked"],
            "hardened_jobs": [row["id"] for row in job_rows if row["classification"] == "Hardened"],
            "regressed_jobs": [row["id"] for row in job_rows if row["classification"] == "Regressed"],
        },
    }

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {ns.out}")

    if ns.markdown_out:
        md = _build_markdown(payload)
        ns.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        ns.markdown_out.write_text(md, encoding="utf-8")
        print(f"Wrote {ns.markdown_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
