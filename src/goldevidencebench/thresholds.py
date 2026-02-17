from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Issue:
    check_id: str
    metric_path: str
    status: str
    message: str
    severity: str


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or "checks" not in data:
        raise ValueError("config must be an object with a 'checks' list")
    if not isinstance(data["checks"], list):
        raise ValueError("'checks' must be a list")
    return data


def _get_path(summary: dict[str, Any], path: str) -> Any:
    current: Any = summary
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _condition_met(summary: dict[str, Any], condition: dict[str, Any]) -> bool:
    path = condition.get("path")
    if not isinstance(path, str) or not path.strip():
        return False
    raw_value = _get_path(summary, path)
    if raw_value is None:
        return False
    if "equals" in condition:
        return raw_value == condition.get("equals")
    value = _as_float(raw_value)
    if value is None:
        return False
    min_value = condition.get("min")
    max_value = condition.get("max")
    if min_value is not None and value < float(min_value):
        return False
    if max_value is not None and value > float(max_value):
        return False
    return True


def _skip_metric(summary: dict[str, Any], metric: dict[str, Any]) -> bool:
    skip_if = metric.get("skip_if")
    if isinstance(skip_if, list):
        if not skip_if:
            return False
        return all(
            isinstance(condition, dict) and _condition_met(summary, condition)
            for condition in skip_if
        )
    if isinstance(skip_if, dict):
        if "all" in skip_if and isinstance(skip_if["all"], list):
            return all(
                isinstance(condition, dict) and _condition_met(summary, condition)
                for condition in skip_if["all"]
            )
        if "any" in skip_if and isinstance(skip_if["any"], list):
            return any(
                isinstance(condition, dict) and _condition_met(summary, condition)
                for condition in skip_if["any"]
            )
        return _condition_met(summary, skip_if)
    return False


def _evaluate_checks(
    config: dict[str, Any],
    *,
    root: Path,
    profile: str,
    strict_optional: bool,
) -> tuple[list[Issue], int]:
    if profile not in {"release", "fastlocal"}:
        raise ValueError(f"unsupported threshold profile: {profile}")
    issues: list[Issue] = []
    error_count = 0
    for check in config.get("checks", []):
        check_id = str(check.get("id", "unknown"))
        severity = str(check.get("severity", "error")).lower()
        required_summary = bool(check.get("required_summary", True))
        summary_path = root / Path(str(check.get("summary_path", "")))
        if not summary_path.exists():
            if not required_summary:
                issues.append(
                    Issue(
                        check_id=check_id,
                        metric_path="summary_path",
                        status="not_applicable",
                        message=f"optional summary missing at {summary_path}",
                        severity=severity,
                    )
                )
                continue
            if profile == "fastlocal" and severity != "error":
                issues.append(
                    Issue(
                        check_id=check_id,
                        metric_path="summary_path",
                        status="not_applicable",
                        message=f"summary missing in fastlocal profile at {summary_path}",
                        severity=severity,
                    )
                )
                continue
            issues.append(
                Issue(
                    check_id=check_id,
                    metric_path="summary_path",
                    status="missing",
                    message=f"missing summary.json at {summary_path}",
                    severity=severity,
                )
            )
            if severity == "error":
                error_count += 1
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        metrics = check.get("metrics", [])
        for metric in metrics:
            metric_path = str(metric.get("path", ""))
            if _skip_metric(summary, metric):
                issues.append(
                    Issue(
                        check_id=check_id,
                        metric_path=metric_path,
                        status="skipped",
                        message="skipped (condition met)",
                        severity=severity,
                    )
                )
                continue
            allow_missing = bool(metric.get("allow_missing", False))
            metric_required = True
            if "required" in metric:
                metric_required = bool(metric.get("required", True))
            elif "allow_missing" in metric:
                metric_required = not allow_missing
            strict_optional_missing = bool(metric.get("strict_optional_missing", True))
            if strict_optional and not metric_required and strict_optional_missing:
                metric_required = True
            raw_value = _get_path(summary, metric_path) if metric_path else None
            value = _as_float(raw_value)
            if value is None:
                if not metric_required:
                    issues.append(
                        Issue(
                            check_id=check_id,
                            metric_path=metric_path,
                            status="skipped",
                            message="missing metric (allowed)",
                            severity=severity,
                        )
                    )
                    continue
                if profile == "fastlocal":
                    issues.append(
                        Issue(
                            check_id=check_id,
                            metric_path=metric_path,
                            status="not_applicable",
                            message="optional metric missing (fastlocal profile)",
                            severity=severity,
                        )
                    )
                    continue
                issues.append(
                    Issue(
                        check_id=check_id,
                        metric_path=metric_path,
                        status="missing",
                        message="missing metric",
                        severity=severity,
                    )
                )
                if severity == "error":
                    error_count += 1
                continue
            min_value = metric.get("min")
            max_value = metric.get("max")
            failed = False
            if min_value is not None and value < float(min_value):
                issues.append(
                    Issue(
                        check_id=check_id,
                        metric_path=metric_path,
                        status="fail",
                        message=f"{value:.4f} < min {float(min_value):.4f}",
                        severity=severity,
                    )
                )
                failed = True
            if max_value is not None and value > float(max_value):
                issues.append(
                    Issue(
                        check_id=check_id,
                        metric_path=metric_path,
                        status="fail",
                        message=f"{value:.4f} > max {float(max_value):.4f}",
                        severity=severity,
                    )
                )
                failed = True
            if not failed:
                issues.append(
                    Issue(
                        check_id=check_id,
                        metric_path=metric_path,
                        status="pass",
                        message=f"{value:.4f}",
                        severity=severity,
                    )
                )
            if failed and severity == "error":
                error_count += 1
    return issues, error_count


def evaluate_checks(
    config: dict[str, Any],
    *,
    root: Path,
    profile: str = "release",
    strict_optional: bool = False,
) -> tuple[list[Issue], int]:
    return _evaluate_checks(config, root=root, profile=profile, strict_optional=strict_optional)


def format_issues(issues: list[Issue]) -> str:
    if not issues:
        return "No checks configured."
    lines = []
    for issue in issues:
        if issue.status in {"fail", "missing"}:
            prefix = f"FAIL({issue.severity})" if issue.status == "fail" else f"MISSING({issue.severity})"
        elif issue.status == "not_applicable":
            prefix = "N/A"
        elif issue.status == "skipped":
            prefix = "SKIP"
        else:
            prefix = "PASS"
        lines.append(
            f"[{prefix}] {issue.check_id} {issue.metric_path} - {issue.message}"
        )
    return "\n".join(lines)
