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
            "Build a capability-delta report that compares before vs after release "
            "artifacts and classifies jobs as Unlocked/Hardened/Unchanged/Regressed."
        )
    )
    parser.add_argument(
        "--jobs-config",
        type=Path,
        default=Path("configs/capability_delta_jobs.json"),
        help="Capability jobs config JSON.",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("runs"),
        help="Runs root containing release_check_* directories and latest pointers.",
    )
    parser.add_argument(
        "--after-release-dir",
        type=Path,
        default=None,
        help="Release directory for the after snapshot (defaults to runs/latest_release pointer).",
    )
    parser.add_argument(
        "--before-release-dir",
        type=Path,
        default=None,
        help="Release directory for the baseline snapshot (defaults to most recent previous release).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/capability_delta_report_latest.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("runs/capability_delta_report_latest.md"),
        help="Output markdown report path.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when any job is classified as Regressed.",
    )
    parser.add_argument(
        "--allow-missing-after-matrix",
        action="store_true",
        help=(
            "Allow missing <after_release_dir>/release_reliability_matrix.json by "
            "degrading to NO_BASELINE mode instead of failing."
        ),
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _read_pointer(path: Path) -> Path | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return None
    return Path(text)


def _release_candidates(runs_root: Path) -> list[Path]:
    if not runs_root.exists():
        return []
    return sorted(
        [p for p in runs_root.glob("release_check_*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _snapshot_path(release_dir: Path) -> Path:
    return release_dir / "release_quality_snapshot.json"


def _matrix_path(release_dir: Path) -> Path:
    return release_dir / "release_reliability_matrix.json"


def _resolve_after_release_dir(ns: argparse.Namespace) -> Path:
    if ns.after_release_dir is not None:
        return ns.after_release_dir
    pointer_path = ns.runs_root / "latest_release"
    pointed = _read_pointer(pointer_path)
    if pointed is not None:
        return pointed
    candidates = _release_candidates(ns.runs_root)
    if not candidates:
        raise FileNotFoundError(
            "Unable to resolve after release dir. Provide --after-release-dir or create runs/latest_release."
        )
    return candidates[0]


def _resolve_before_release_dir(ns: argparse.Namespace, after_release_dir: Path) -> Path | None:
    if ns.before_release_dir is not None:
        return ns.before_release_dir
    after_resolved = after_release_dir.resolve()
    for candidate in _release_candidates(ns.runs_root):
        if candidate.resolve() == after_resolved:
            continue
        if _snapshot_path(candidate).exists() and _matrix_path(candidate).exists():
            return candidate
    return None


def _flatten_scalars(prefix: str, payload: dict[str, Any], out: dict[str, Any]) -> None:
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[f"{prefix}{key}"] = value


def _build_metric_map(snapshot: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["snapshot.status"] = snapshot.get("status")

    metrics = snapshot.get("metrics")
    if isinstance(metrics, dict):
        _flatten_scalars("metrics.", metrics, out)

    gates = snapshot.get("gates")
    if isinstance(gates, dict):
        _flatten_scalars("gates.", gates, out)

    integrity = snapshot.get("integrity")
    if isinstance(integrity, dict):
        _flatten_scalars("integrity.", integrity, out)

    out["matrix.status"] = matrix.get("status")
    coverage = matrix.get("coverage")
    if isinstance(coverage, dict):
        _flatten_scalars("matrix.coverage.", coverage, out)
        missing = coverage.get("missing_families")
        if isinstance(missing, list):
            out["matrix.missing_count"] = len(missing)

    failing = matrix.get("failing_families")
    if isinstance(failing, list):
        out["matrix.failing_count"] = len(failing)

    families = matrix.get("families")
    if isinstance(families, list):
        for row in families:
            if not isinstance(row, dict):
                continue
            family_id = str(row.get("id") or "").strip()
            if not family_id:
                continue
            status = str(row.get("status") or "UNKNOWN")
            out[f"family.{family_id}.status"] = status
            out[f"family.{family_id}.is_pass"] = 1.0 if status == "PASS" else 0.0
            produced = row.get("produced_in_this_run")
            if isinstance(produced, bool):
                out[f"family.{family_id}.produced_in_this_run"] = 1.0 if produced else 0.0
            failures = row.get("failures")
            if isinstance(failures, list):
                out[f"family.{family_id}.failure_count"] = len(failures)
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
    lines.append("# Capability Delta Report")
    lines.append("")
    lines.append(f"- generated_at: `{payload['generated_at_utc']}`")
    lines.append(f"- status: `{payload['status']}`")
    lines.append(f"- after_release_dir: `{payload['after_release_dir']}`")
    lines.append(f"- before_release_dir: `{payload.get('before_release_dir')}`")
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
        raise ValueError("Capability jobs config must include a non-empty jobs[] list.")

    after_release_dir = _resolve_after_release_dir(ns)
    before_release_dir = _resolve_before_release_dir(ns, after_release_dir)

    after_snapshot_path = _snapshot_path(after_release_dir)
    after_matrix_path = _matrix_path(after_release_dir)
    if not after_snapshot_path.exists():
        raise FileNotFoundError(
            f"After release artifacts missing. Needed: {after_snapshot_path}, {after_matrix_path}"
        )

    degraded_missing_after_matrix = False
    if not after_matrix_path.exists():
        if ns.allow_missing_after_matrix:
            degraded_missing_after_matrix = True
        else:
            raise FileNotFoundError(
                f"After release artifacts missing. Needed: {after_snapshot_path}, {after_matrix_path}"
            )

    after_snapshot = _read_json(after_snapshot_path)
    if degraded_missing_after_matrix:
        after_matrix = {
            "status": "MISSING",
            "coverage": {
                "required_total": 0,
                "produced_total": 0,
                "missing_families": [],
            },
            "failing_families": [],
            "families": [],
        }
    else:
        after_matrix = _read_json(after_matrix_path)
    after_metrics = _build_metric_map(after_snapshot, after_matrix)

    has_before = before_release_dir is not None and not degraded_missing_after_matrix
    if degraded_missing_after_matrix:
        before_release_dir = None

    before_metrics: dict[str, Any] = {}
    before_snapshot: dict[str, Any] | None = None
    before_matrix: dict[str, Any] | None = None
    if has_before:
        before_snapshot_path = _snapshot_path(before_release_dir)
        before_matrix_path = _matrix_path(before_release_dir)
        if before_snapshot_path.exists() and before_matrix_path.exists():
            before_snapshot = _read_json(before_snapshot_path)
            before_matrix = _read_json(before_matrix_path)
            before_metrics = _build_metric_map(before_snapshot, before_matrix)
        else:
            has_before = False

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
            raise ValueError("Each capability job must define id.")
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
        "benchmark": "capability_delta_report",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "inputs": {
            "jobs_config": str(ns.jobs_config),
            "after_release_dir": str(after_release_dir),
            "before_release_dir": str(before_release_dir) if before_release_dir is not None else None,
            "allow_missing_after_matrix": bool(ns.allow_missing_after_matrix),
        },
        "policy": {
            "unlock": policy.get("unlock", {}),
            "harden": policy.get("harden", {}),
            "regress": policy.get("regress", {}),
            "risk_penalty_lambda": risk_penalty_lambda,
        },
        "after_release_dir": str(after_release_dir),
        "before_release_dir": str(before_release_dir) if before_release_dir is not None else None,
        "jobs": job_rows,
        "summary": {
            "has_before_release": has_before,
            "job_count": len(job_rows),
            "classification_counts": counts,
            "utility_delta": utility_delta_total if has_before else None,
            "unlocked_jobs": [row["id"] for row in job_rows if row["classification"] == "Unlocked"],
            "hardened_jobs": [row["id"] for row in job_rows if row["classification"] == "Hardened"],
            "regressed_jobs": [row["id"] for row in job_rows if row["classification"] == "Regressed"],
            "degraded_missing_after_matrix": degraded_missing_after_matrix,
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

    if ns.fail_on_regression and counts["Regressed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
