from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FamilySpec:
    family_id: str
    generator: str
    scorer: str
    wrapper: str
    reliability_checker: str
    required_metrics: list[str]
    current_thresholds: dict[str, Any]
    canary_rule: str
    axis: str = "core"
    subfamilies: list[str] | None = None
    reliability_path: str | None = None


FAMILY_SPECS: list[FamilySpec] = [
    FamilySpec(
        family_id="compression_loss_bounded",
        generator="scripts/generate_compression_loss_bounded_family.py",
        scorer="scripts/score_compression_loss_bounded.py",
        wrapper="scripts/run_compression_families.ps1",
        reliability_checker="scripts/check_compression_reliability.py",
        required_metrics=["precision", "recall", "bloat", "parse_rate"],
        current_thresholds={"holdout": {"min_precision": 0.90, "min_recall": 0.90, "max_bloat": 0.20}},
        canary_rule="expected_fail canary; alert when canary exact_rate >= 0.95",
        axis="indexing_reassembly",
        reliability_path="runs/compression_reliability_latest.json",
    ),
    FamilySpec(
        family_id="compression_recoverability",
        generator="scripts/generate_compression_recoverability_family.py",
        scorer="scripts/score_compression_recoverability.py",
        wrapper="scripts/run_compression_families.ps1",
        reliability_checker="scripts/check_compression_reliability.py",
        required_metrics=["value_acc", "exact_acc", "entailment", "cite_f1", "parse_rate"],
        current_thresholds={"holdout": {"min_value_acc": 0.90, "min_exact_acc": 0.90, "min_cite_f1": 0.90}},
        canary_rule="expected_fail canary; alert when canary exact_rate >= 0.95",
        axis="indexing_reassembly",
        reliability_path="runs/compression_reliability_latest.json",
    ),
    FamilySpec(
        family_id="novel_continuity",
        generator="scripts/generate_novel_continuity_family.py",
        scorer="scripts/score_novel_continuity.py",
        wrapper="scripts/run_novel_continuity_family.ps1",
        reliability_checker="scripts/check_novel_continuity_reliability.py",
        required_metrics=["value_acc", "exact_acc", "cite_f1", "identity_acc", "timeline_acc", "constraint_acc"],
        current_thresholds={
            "holdout": {
                "min_value_acc": 0.85,
                "min_exact_acc": 0.85,
                "min_cite_f1_target": 0.85,
                "min_identity_acc": 0.80,
                "min_timeline_acc": 0.80,
                "min_constraint_acc": 0.80,
            }
        },
        canary_rule="expected_fail canary; alert when canary exact_rate >= configured threshold",
        axis="novel_continuity",
        reliability_path="runs/novel_continuity_reliability_latest.json",
    ),
    FamilySpec(
        family_id="novel_continuity_long_horizon",
        generator="scripts/generate_novel_continuity_long_horizon_family.py",
        scorer="scripts/score_novel_continuity_long_horizon.py",
        wrapper="scripts/run_novel_continuity_long_horizon_family.ps1",
        reliability_checker="scripts/check_novel_continuity_long_horizon_reliability.py",
        required_metrics=[
            "value_acc",
            "exact_acc",
            "cite_f1",
            "identity_acc",
            "timeline_acc",
            "constraint_acc",
            "long_gap_acc",
            "high_contradiction_acc",
            "delayed_dependency_acc",
            "repair_transition_acc",
        ],
        current_thresholds={
            "holdout": {
                "min_value_acc": 0.85,
                "min_exact_acc": 0.85,
                "min_cite_f1_target": 0.85,
                "min_identity_acc": 0.80,
                "min_timeline_acc": 0.80,
                "min_constraint_acc": 0.80,
                "min_long_gap_acc": 0.80,
                "min_high_contradiction_acc": 0.80,
                "min_delayed_dependency_acc": 0.80,
                "min_repair_transition_acc": 0.80,
            }
        },
        canary_rule="expected_fail canary; alert when canary exact_rate >= configured threshold",
        axis="novel_continuity",
        reliability_path="runs/novel_continuity_long_horizon_reliability_latest.json",
    ),
    FamilySpec(
        family_id="authority_under_interference",
        generator="scripts/generate_authority_under_interference_family.py",
        scorer="scripts/score_authority_under_interference.py",
        wrapper="scripts/run_authority_under_interference_family.ps1",
        reliability_checker="scripts/check_authority_under_interference_reliability.py",
        required_metrics=[
            "value_acc",
            "exact_acc",
            "cite_f1",
            "latest_support_hit_rate",
            "note_citation_rate",
            "stale_citation_rate",
            "authority_violation_rate",
        ],
        current_thresholds={
            "holdout": {
                "min_value_acc": 0.90,
                "min_exact_acc": 0.90,
                "min_cite_f1": 0.85,
                "min_latest_support_hit_rate": 0.90,
                "max_note_citation_rate": 0.05,
                "max_stale_citation_rate": 0.05,
                "max_authority_violation_rate": 0.05,
            }
        },
        canary_rule="expected_fail canary; alert when canary exact_rate exceeds configured max",
        axis="authority_interference",
        reliability_path="runs/authority_under_interference_reliability_latest.json",
    ),
    FamilySpec(
        family_id="compression_roundtrip_generalization",
        generator="scripts/generate_compression_roundtrip_generalization_family.py",
        scorer="scripts/score_compression_roundtrip_generalization.py",
        wrapper="scripts/run_compression_roundtrip_generalization_family.ps1",
        reliability_checker="scripts/check_compression_roundtrip_generalization_reliability.py",
        required_metrics=[
            "value_acc",
            "exact_acc",
            "cite_f1",
            "direct_acc",
            "aggregate_acc",
            "exception_acc",
            "negation_acc",
            "tail_key_acc",
            "null_target_acc",
            "nonnull_target_acc",
            "large_snapshot_acc",
        ],
        current_thresholds={
            "observe": {
                "min_value_acc": 0.65,
                "min_exact_acc": 0.65,
                "min_cite_f1": 0.50,
                "min_exception_acc": 0.20,
                "min_large_snapshot_acc": 0.00,
            },
            "target": {
                "min_value_acc": 0.85,
                "min_exact_acc": 0.85,
                "min_cite_f1": 0.85,
                "min_exception_acc": 0.80,
                "min_large_snapshot_acc": 0.80,
            },
        },
        canary_rule="expected_fail canary; alert when canary exact_rate >= configured threshold",
        axis="indexing_reassembly",
        reliability_path="runs/compression_roundtrip_generalization_reliability_latest.json",
    ),
    FamilySpec(
        family_id="myopic_planning_traps",
        generator="scripts/generate_myopic_planning_traps_family.py",
        scorer="scripts/score_myopic_planning_traps.py",
        wrapper="scripts/run_myopic_planning_traps_family.ps1",
        reliability_checker="scripts/check_myopic_planning_traps_reliability.py",
        required_metrics=[
            "value_acc",
            "exact_acc",
            "cite_f1",
            "horizon_success_rate",
            "recovery_rate",
            "trap_entry_rate",
            "first_error_step_mean",
        ],
        current_thresholds={
            "observe": {
                "min_value_acc": 0.60,
                "min_exact_acc": 0.60,
                "min_cite_f1": 0.40,
                "min_horizon_success_rate": 0.60,
                "min_recovery_rate": 0.50,
                "max_trap_entry_rate": 0.40,
                "min_first_error_step_mean": 1.50,
            },
            "target": {
                "min_value_acc": 0.85,
                "min_exact_acc": 0.85,
                "min_cite_f1": 0.80,
                "min_horizon_success_rate": 0.85,
                "min_recovery_rate": 0.80,
                "max_trap_entry_rate": 0.15,
                "min_first_error_step_mean": 2.50,
            },
        },
        canary_rule="expected_fail canary; alert when canary exact_rate >= configured threshold",
        axis="myopic_planning",
        reliability_path="runs/myopic_planning_traps_reliability_latest.json",
    ),
    FamilySpec(
        family_id="authority_under_interference_hardening",
        generator="scripts/generate_authority_under_interference_hardening_family.py",
        scorer="scripts/score_authority_under_interference_hardening.py",
        wrapper="scripts/run_authority_under_interference_hardening_family.ps1",
        reliability_checker="scripts/check_authority_under_interference_hardening_reliability.py",
        required_metrics=[
            "value_acc",
            "exact_acc",
            "cite_f1",
            "latest_support_hit_rate",
            "authority_violation_rate",
        ],
        current_thresholds={
            "holdout": {
                "min_value_acc": 0.92,
                "min_exact_acc": 0.92,
                "min_cite_f1": 0.88,
                "min_latest_support_hit_rate": 0.92,
                "max_authority_violation_rate": 0.03,
            }
        },
        canary_rule="expected_fail canary; alert when canary exact_rate >= configured max",
        axis="authority_interference",
        reliability_path="runs/authority_under_interference_hardening_reliability_latest.json",
    ),
    FamilySpec(
        family_id="referential_indexing_suite",
        generator="scripts/generate_referential_indexing_suite_family.py",
        scorer="scripts/score_referential_indexing_suite.py",
        wrapper="scripts/run_referential_indexing_suite_family.ps1",
        reliability_checker="scripts/check_referential_indexing_suite_reliability.py",
        required_metrics=[
            "pointer_set_size",
            "part_coverage_recall",
            "pointer_precision",
            "pointer_recall",
            "reassembly_fidelity",
            "hallucinated_expansion_rate",
            "stale_pointer_override_rate",
            "lookup_depth_cost",
        ],
        current_thresholds={
            "observe": {
                "min_value_acc": 0.55,
                "min_exact_acc": 0.55,
                "min_cite_f1": 0.35,
                "min_exception_acc": 0.20,
                "min_large_snapshot_acc": 0.00,
            },
            "target": {
                "min_value_acc": 0.85,
                "min_exact_acc": 0.85,
                "min_cite_f1": 0.85,
                "min_exception_acc": 0.80,
                "min_large_snapshot_acc": 0.80,
            },
        },
        canary_rule="expected_fail canary; alert when canary exact_rate >= configured threshold",
        axis="indexing_reassembly",
        subfamilies=[
            "index_loss_bounded",
            "reassembly_recoverability",
            "minimal_pointer_set",
            "reconstruction_fidelity",
            "no_invention_expansion",
            "stale_pointer_conflict",
            "wrong_hub_attraction",
            "assembly_order_traps",
            "wrong_address_traps",
        ],
        reliability_path="runs/referential_indexing_suite_reliability_latest.json",
    ),
    FamilySpec(
        family_id="epistemic_calibration_suite",
        generator="scripts/generate_epistemic_calibration_suite_family.py",
        scorer="scripts/score_epistemic_calibration_suite.py",
        wrapper="scripts/run_epistemic_calibration_suite_family.ps1",
        reliability_checker="scripts/check_epistemic_calibration_suite_reliability.py",
        required_metrics=[
            "overclaim_rate",
            "abstain_precision",
            "abstain_recall",
            "abstain_f1",
            "ece",
            "brier",
            "selective_accuracy_at_coverage",
            "needed_info_recall",
            "kkyi",
        ],
        current_thresholds={
            "target": {
                "min_kkyi": 0.72,
                "max_overclaim_rate": 0.15,
                "min_abstain_f1": 0.70,
                "max_ece": 0.20,
                "max_brier": 0.25,
                "min_selective_accuracy_at_coverage": 0.85,
                "min_needed_info_recall": 0.75,
            }
        },
        canary_rule="expected_fail canary; alert when canary KKYI is too high",
        axis="epistemic_calibration",
        subfamilies=[
            "known_answerable",
            "unknown_unanswerable",
            "near_miss_familiar",
            "contradictory_evidence",
            "missing_key_dependency",
            "confidence_inversion",
        ],
        reliability_path="runs/epistemic_calibration_suite_reliability_latest.json",
    ),
]


MODE_TAXONOMY: dict[str, set[str]] = {
    "compression_loss_bounded": {"precision_loss", "recall_loss", "bloat_excess", "parse_failure"},
    "compression_recoverability": {"value_mismatch", "exact_mismatch", "citation_gap", "parse_failure"},
    "novel_continuity": {"identity_break", "timeline_break", "constraint_break", "citation_gap"},
    "novel_continuity_long_horizon": {
        "long_gap_break",
        "contradiction_break",
        "delayed_dependency_break",
        "repair_transition_break",
        "citation_gap",
    },
    "authority_under_interference": {
        "latest_miss",
        "note_citation",
        "stale_citation",
        "authority_violation",
    },
    "compression_roundtrip_generalization": {
        "direct_miss",
        "aggregate_miss",
        "exception_miss",
        "negation_miss",
        "tail_key_miss",
        "null_target_miss",
        "nonnull_target_miss",
        "large_snapshot_miss",
        "citation_gap",
    },
    "myopic_planning_traps": {
        "trap_entry",
        "horizon_failure",
        "recovery_failure",
        "counterfactual_failure",
        "first_error_early",
    },
    "authority_under_interference_hardening": {
        "hard_decoy_override",
        "deep_stale_chain_miss",
        "ambiguity_abstain_failure",
    },
    "referential_indexing_suite": {
        "index_loss_bounded_miss",
        "reassembly_recoverability_miss",
        "minimal_pointer_set_miss",
        "reconstruction_fidelity_miss",
        "no_invention_expansion_miss",
        "stale_pointer_conflict_miss",
        "wrong_hub_attraction_miss",
        "assembly_order_traps_miss",
        "wrong_address_traps_miss",
        "hallucinated_expansion",
        "stale_pointer_override",
    },
    "epistemic_calibration_suite": {
        "known_answerable_miss",
        "unknown_unanswerable_miss",
        "near_miss_familiar_miss",
        "contradictory_evidence_miss",
        "missing_key_dependency_miss",
        "confidence_inversion_miss",
        "overclaim",
        "schema_noncompliance",
        "missing_needed_info",
    },
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build family compatibility matrix + orthogonality matrix + markdown report."
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root.")
    parser.add_argument("--out-dir", type=Path, default=Path("runs/codex_compat"), help="Output directory.")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/CODEX_COMPAT_REPORT.md"),
        help="Markdown report path.",
    )
    return parser.parse_args()


def _safe_read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig")


def _normalize_mode_id(raw: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return token[:96] if token else "unknown"


def _map_failure_to_mode(family_id: str, failure: str) -> str:
    text = failure.lower()
    if "cite" in text:
        return "citation_gap"
    if "exception" in text:
        return "exception_miss"
    if "tail" in text:
        return "tail_key_miss"
    if "large_snapshot" in text:
        return "large_snapshot_miss"
    if "identity" in text:
        return "identity_break"
    if "timeline" in text:
        return "timeline_break"
    if "constraint" in text:
        return "constraint_break"
    if "long_gap" in text:
        return "long_gap_break"
    if "contradiction" in text:
        return "contradiction_break"
    if "delayed_dependency" in text:
        return "delayed_dependency_break"
    if "repair_transition" in text:
        return "repair_transition_break"
    if "authority_violation" in text:
        return "authority_violation"
    if "note_citation" in text:
        return "note_citation"
    if "stale_citation" in text:
        return "stale_citation"
    if "latest_support_hit" in text:
        return "latest_miss"
    if "trap_entry" in text:
        return "trap_entry"
    if "horizon" in text:
        return "horizon_failure"
    if "recovery" in text:
        return "recovery_failure"
    if "first_error" in text:
        return "first_error_early"
    if "precision" in text:
        return "precision_loss"
    if "recall" in text:
        return "recall_loss"
    if "bloat" in text:
        return "bloat_excess"
    if "parse" in text:
        return "parse_failure"
    if "value_acc" in text:
        return "value_mismatch"
    if "exact_acc" in text:
        return "exact_mismatch"
    return _normalize_mode_id(f"{family_id}_{failure}")


def _load_reliability_modes(repo_root: Path, spec: FamilySpec) -> set[str]:
    if not spec.reliability_path:
        return set()
    path = repo_root / spec.reliability_path
    if not path.exists():
        return set()
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return set()
    if not isinstance(obj, dict):
        return set()

    modes: set[str] = set()
    failures = obj.get("failures")
    if isinstance(failures, list):
        for item in failures:
            if isinstance(item, str):
                modes.add(_map_failure_to_mode(spec.family_id, item))

    explicit = obj.get("failure_mode_ids")
    if isinstance(explicit, list):
        for item in explicit:
            if isinstance(item, str):
                modes.add(_normalize_mode_id(item))

    if not modes and spec.family_id == "compression_loss_bounded" and isinstance(failures, list):
        for item in failures:
            if isinstance(item, str) and "clb" in item.lower():
                modes.add(_map_failure_to_mode(spec.family_id, item))

    if not modes and spec.family_id == "compression_recoverability" and isinstance(failures, list):
        for item in failures:
            if isinstance(item, str) and "crv" in item.lower():
                modes.add(_map_failure_to_mode(spec.family_id, item))

    return modes


def _orthogonality(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 1.0
    inter = a & b
    return 1.0 - (len(inter) / len(union))


def _read_reliability_status(repo_root: Path, spec: FamilySpec) -> tuple[bool, str, str]:
    if not spec.reliability_path:
        return False, "MISSING", "no reliability path configured"
    path = repo_root / spec.reliability_path
    if not path.exists():
        return False, "MISSING", f"missing file: {path}"
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return False, "ERROR", str(exc)
    if not isinstance(obj, dict):
        return False, "ERROR", "invalid JSON object"
    status = obj.get("status")
    if isinstance(status, str):
        return True, status, ""
    return True, "UNKNOWN", "missing status field"


def main() -> int:
    ns = _parse_args()
    repo_root = ns.repo_root.resolve()
    out_dir = (repo_root / ns.out_dir).resolve()
    report_path = (repo_root / ns.report_path).resolve()

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    readme_text = _safe_read(repo_root / "README.md")
    trap_plan_text = _safe_read(repo_root / "docs/TRAP_PLAN.md")
    trap_families_text = _safe_read(repo_root / "docs/TRAP_FAMILIES.md")

    matrix_rows: list[dict[str, Any]] = []
    family_mode_sets: dict[str, set[str]] = {}
    mismatches: list[str] = []
    backlog_rows: list[dict[str, Any]] = []

    for spec in FAMILY_SPECS:
        paths = [spec.generator, spec.scorer, spec.wrapper, spec.reliability_checker]
        missing_scripts = [p for p in paths if not (repo_root / p).exists()]
        scripts_present = len(missing_scripts) == 0

        docs_hits = {
            "README.md": spec.family_id in readme_text,
            "docs/TRAP_PLAN.md": spec.family_id in trap_plan_text,
            "docs/TRAP_FAMILIES.md": spec.family_id in trap_families_text,
        }
        docs_present = all(docs_hits.values())
        reliability_exists, reliability_status, reliability_note = _read_reliability_status(repo_root, spec)

        mismatch_notes: list[str] = []
        if missing_scripts:
            mismatch_notes.append("missing scripts: " + ", ".join(missing_scripts))
        missing_docs = [name for name, hit in docs_hits.items() if not hit]
        if missing_docs:
            mismatch_notes.append("missing docs mention: " + ", ".join(missing_docs))
        if reliability_note:
            mismatch_notes.append("reliability: " + reliability_note)

        observed_modes = _load_reliability_modes(repo_root, spec)
        default_modes = MODE_TAXONOMY.get(spec.family_id, set())
        active_modes = observed_modes if observed_modes else set(default_modes)
        family_mode_sets[spec.family_id] = active_modes

        if mismatch_notes:
            mismatches.append(f"{spec.family_id}: " + " | ".join(mismatch_notes))

        matrix_rows.append(
            {
                "family_id": spec.family_id,
                "axis": spec.axis,
                "subfamilies": spec.subfamilies or [],
                "generator": spec.generator,
                "scorer": spec.scorer,
                "wrapper": spec.wrapper,
                "reliability_checker": spec.reliability_checker,
                "required_metrics": spec.required_metrics,
                "current_thresholds": spec.current_thresholds,
                "canary_rule": spec.canary_rule,
                "docs_present": docs_present,
                "scripts_present": scripts_present,
                "docs_hits": docs_hits,
                "reliability_file_exists": reliability_exists,
                "reliability_status": reliability_status,
                "scaffold_complete": scripts_present and docs_present,
                "hardened": reliability_exists and reliability_status == "PASS",
                "mode_ids_source": "observed_failures" if observed_modes else "taxonomy_default",
                "mode_ids": sorted(active_modes),
                "mismatch_notes": mismatch_notes,
            }
        )

        backlog_reasons: list[str] = []
        if not scripts_present:
            backlog_reasons.append("missing_scripts")
        if not docs_present:
            backlog_reasons.append("missing_docs")
        if not reliability_exists:
            backlog_reasons.append("missing_reliability_signal")
        elif reliability_status != "PASS":
            backlog_reasons.append("reliability_not_pass")
        if backlog_reasons:
            backlog_rows.append(
                {
                    "family_id": spec.family_id,
                    "axis": spec.axis,
                    "reasons": backlog_reasons,
                    "mismatch_notes": mismatch_notes,
                    "reliability_status": reliability_status,
                }
            )

    active_families = [row["family_id"] for row in matrix_rows if row["scripts_present"]]
    pairwise: list[dict[str, Any]] = []
    matrix: dict[str, dict[str, float]] = {}

    for family_a in active_families:
        matrix[family_a] = {}
        for family_b in active_families:
            modes_a = family_mode_sets.get(family_a, set())
            modes_b = family_mode_sets.get(family_b, set())
            score = _orthogonality(modes_a, modes_b)
            matrix[family_a][family_b] = score
            if family_a < family_b:
                inter = sorted(modes_a & modes_b)
                union = sorted(modes_a | modes_b)
                pairwise.append(
                    {
                        "family_a": family_a,
                        "family_b": family_b,
                        "intersection": inter,
                        "union_count": len(union),
                        "orthogonality": score,
                    }
                )

    family_matrix_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [
            "README.md",
            "docs/TRAP_PLAN.md",
            "docs/TRAP_FAMILIES.md",
            "scripts/*",
            "runs/*_reliability_latest.json",
        ],
        "rows": matrix_rows,
    }
    orthogonality_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "families": active_families,
        "mode_sets": {k: sorted(v) for k, v in family_mode_sets.items() if k in active_families},
        "pairwise": pairwise,
        "matrix": matrix,
    }

    family_matrix_path = out_dir / "family_matrix.json"
    orthogonality_path = out_dir / "orthogonality_matrix.json"
    backlog_path = out_dir / "scaffold_backlog.json"
    backlog_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_families": len(matrix_rows),
        "unfilled_count": len(backlog_rows),
        "rows": backlog_rows,
    }
    family_matrix_path.write_text(json.dumps(family_matrix_payload, indent=2), encoding="utf-8")
    orthogonality_path.write_text(json.dumps(orthogonality_payload, indent=2), encoding="utf-8")
    backlog_path.write_text(json.dumps(backlog_payload, indent=2), encoding="utf-8")

    mismatch_lines = "\n".join(f"- {m}" for m in mismatches) if mismatches else "- none"
    pair_rows = []
    for item in sorted(pairwise, key=lambda r: (r["orthogonality"], r["family_a"], r["family_b"])):
        pair_rows.append(
            f"| {item['family_a']} | {item['family_b']} | {item['orthogonality']:.3f} | {', '.join(item['intersection']) or '-'} |"
        )
    pair_table = "\n".join(pair_rows) if pair_rows else "| - | - | - | - |"
    backlog_lines = "\n".join(
        f"- `{item['family_id']}` ({item['axis']}): {', '.join(item['reasons'])}"
        for item in backlog_rows
    )
    if not backlog_lines:
        backlog_lines = "- none"

    report = f"""# CODEX Compatibility Report

Generated: {datetime.now(timezone.utc).isoformat()}

## Scope
- Verify family lifecycle compatibility (generator -> scorer -> wrapper -> reliability checker).
- Verify docs/script consistency for trap-family contracts.
- Export orthogonality diagnostics from observed failure modes (fallback: family mode taxonomy).

## Math Contract Used
- Single-run pass: `P[f,r] = 1` iff all required thresholds pass and canary rule holds.
- Reliability: all runs pass + bounded jitter on selected holdout metrics.
- Orthogonality: `1 - |A ∩ B| / |A ∪ B|` over family mode IDs.

## Artifacts
- `runs/codex_compat/family_matrix.json`
- `runs/codex_compat/orthogonality_matrix.json`
- `runs/codex_compat/scaffold_backlog.json`

## Mismatches
{mismatch_lines}

## Unfilled Tracker
{backlog_lines}

## Pairwise Orthogonality
| Family A | Family B | Orthogonality | Intersection |
| --- | --- | ---: | --- |
{pair_table}

## Reproduction Commands
```powershell
python .\\scripts\\build_codex_compat_report.py
python .\\scripts\\build_codex_compat_report.py --out-dir runs/codex_compat --report-path docs/CODEX_COMPAT_REPORT.md
```
"""
    report_path.write_text(report, encoding="utf-8")

    print(f"Wrote {family_matrix_path}")
    print(f"Wrote {orthogonality_path}")
    print(f"Wrote {backlog_path}")
    print(f"Wrote {report_path}")
    print(f"Families analyzed: {len(matrix_rows)}")
    print(f"Unfilled families: {len(backlog_rows)}")
    if mismatches:
        print(f"Mismatches: {len(mismatches)}")
    else:
        print("Mismatches: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
