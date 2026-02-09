from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_FAST_BANDS = {
    "value_acc": 0.005,
    "exact_acc": 0.005,
    "entailment": 0.005,
    "answer_correct_given_selected": 0.005,
    "cite_f1": 0.005,
    "instruction_acc": 0.010,
    "state_integrity_rate": 0.005,
}

_FULL_BANDS = {
    "value_acc": 0.003,
    "exact_acc": 0.003,
    "entailment": 0.003,
    "answer_correct_given_selected": 0.003,
    "cite_f1": 0.003,
    "instruction_acc": 0.007,
    "state_integrity_rate": 0.003,
}

_FAST_DOMAIN_CHECKS = ("domain_stale", "domain_authority", "domain_exception")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check fast-vs-full acceptance bands for rag_benchmark_strict summaries. "
            "Returns exit code 0 on pass and 1 on fail."
        )
    )
    parser.add_argument("--stage", choices=("fast", "full"), required=True, help="Validation stage to enforce.")
    parser.add_argument("--base", type=Path, required=True, help="Base run dir or summary JSON path.")
    parser.add_argument("--other", type=Path, required=True, help="Other run dir or summary JSON path.")
    parser.add_argument(
        "--allow-missing-keys",
        action="store_true",
        help="Skip missing mean keys instead of failing the check.",
    )
    parser.add_argument(
        "--strict-benchmark-name",
        action="store_true",
        help="Require benchmark field to be rag_benchmark_strict in both summaries.",
    )
    return parser.parse_args()


def _load_summary(path: Path) -> tuple[dict[str, Any], Path]:
    candidates: list[Path]
    if path.is_file():
        candidates = [path]
    else:
        candidates = [path / "summary_compact.json", path / "summary.json"]

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON: {candidate} ({exc})") from exc
        if isinstance(payload, dict):
            return payload, candidate
    raise RuntimeError(
        f"Could not locate a summary JSON at {path}. "
        "Expected a file or a run dir containing summary_compact.json or summary.json."
    )


def _means(summary: dict[str, Any]) -> dict[str, float]:
    means = summary.get("means")
    if not isinstance(means, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in means.items():
        if isinstance(val, (int, float)):
            out[key] = float(val)
    return out


def _dataset_map(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = summary.get("datasets")
    if not isinstance(rows, list):
        rows = summary.get("results")
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        if isinstance(row_id, str) and row_id:
            out[row_id] = row
    return out


def _check_domain_hard_checks(other_summary: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_id = _dataset_map(other_summary)
    for dataset_id in _FAST_DOMAIN_CHECKS:
        row = by_id.get(dataset_id)
        if row is None:
            failures.append(f"missing dataset: {dataset_id}")
            continue
        exact = row.get("exact_acc")
        if not isinstance(exact, (int, float)):
            failures.append(f"{dataset_id}.exact_acc missing/non-numeric")
            continue
        if float(exact) < 1.0:
            failures.append(f"{dataset_id}.exact_acc={float(exact):.6f} (expected 1.000000)")
    return failures


def _check_mean_bands(
    *,
    stage: str,
    base_summary: dict[str, Any],
    other_summary: dict[str, Any],
    allow_missing_keys: bool,
) -> tuple[list[str], list[str]]:
    base_means = _means(base_summary)
    other_means = _means(other_summary)
    bands = _FAST_BANDS if stage == "fast" else _FULL_BANDS
    lines: list[str] = []
    failures: list[str] = []

    for key, band in bands.items():
        base_val = base_means.get(key)
        other_val = other_means.get(key)
        if base_val is None or other_val is None:
            msg = f"{key}: missing in means"
            if allow_missing_keys:
                lines.append(f"[SKIP] {msg}")
                continue
            failures.append(msg)
            lines.append(f"[FAIL] {msg}")
            continue
        delta = other_val - base_val
        ok = delta >= -band
        state = "PASS" if ok else "FAIL"
        lines.append(
            f"[{state}] {key}: {base_val:.6f} -> {other_val:.6f} "
            f"(delta {delta:+.6f}, min {-band:+.6f})"
        )
        if not ok:
            failures.append(f"{key}: delta {delta:+.6f} < {-band:+.6f}")
    return lines, failures


def main() -> int:
    ns = _parse_args()
    try:
        base_summary, base_source = _load_summary(ns.base)
        other_summary, other_source = _load_summary(ns.other)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("RAG acceptance band check")
    print(f"Stage: {ns.stage}")
    print(f"Base: {base_source}")
    print(f"Other: {other_source}")

    failures: list[str] = []

    if ns.strict_benchmark_name:
        expected = "rag_benchmark_strict"
        base_bench = base_summary.get("benchmark")
        other_bench = other_summary.get("benchmark")
        if base_bench != expected:
            failures.append(f"base benchmark={base_bench!r}, expected {expected!r}")
        if other_bench != expected:
            failures.append(f"other benchmark={other_bench!r}, expected {expected!r}")

    if ns.stage == "fast":
        domain_failures = _check_domain_hard_checks(other_summary)
        if domain_failures:
            print("Domain hard checks:")
            for item in domain_failures:
                print(f"[FAIL] {item}")
            failures.extend(domain_failures)
        else:
            print("Domain hard checks:")
            for dataset_id in _FAST_DOMAIN_CHECKS:
                print(f"[PASS] {dataset_id}.exact_acc=1.000000")

    lines, band_failures = _check_mean_bands(
        stage=ns.stage,
        base_summary=base_summary,
        other_summary=other_summary,
        allow_missing_keys=ns.allow_missing_keys,
    )
    print("Mean band checks:")
    for line in lines:
        print(line)
    failures.extend(band_failures)

    if failures:
        print(f"RESULT: FAIL ({len(failures)} issue(s))")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
