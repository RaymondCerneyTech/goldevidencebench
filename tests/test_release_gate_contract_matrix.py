from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from goldevidencebench import schema_validation


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_powershell_file(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("pwsh/powershell executable is required for release matrix integration tests")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _touch_json(path: Path, payload: dict) -> None:
    _write_json(path, payload)


def _required_ui_baseline_outputs() -> list[str]:
    return [
        "runs/ui_minipilot_notepad_search.json",
        "runs/ui_minipilot_form_search.json",
        "runs/ui_minipilot_table_search.json",
        "runs/ui_minipilot_notepad_ambiguous_search.json",
        "runs/ui_minipilot_notepad_wrong_directory_detour_search.json",
        "runs/ui_minipilot_local_optimum_search.json",
        "runs/ui_minipilot_local_optimum_delayed_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_blocking_modal_required_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_disabled_primary_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_confirm_then_apply_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_tab_state_reset_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_context_switch_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_stale_tab_state_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_form_validation_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_window_focus_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_checkbox_gate_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_panel_toggle_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_accessibility_label_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_section_path_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_section_path_conflict_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_destructive_confirm_ambiguous_search.json",
        "runs/ui_minipilot_local_optimum_role_conflict_ambiguous_search.json",
    ]


def _make_contract(path: Path, *, artifact_path: Path, freshness_policy: str) -> None:
    payload = {
        "contract_id": "release_gate_contract",
        "version": "test",
        "strict_release": {
            "freshness_policy": freshness_policy,
            "canary_policy": "strict",
            "required_reliability_families": [
                {
                    "id": "novel_continuity",
                    "artifact_path": str(artifact_path),
                    "stage": "target",
                    "allowed_statuses": ["PASS"],
                }
            ],
            "utility_gate": {
                "required": False,
                "producer_mode": "deferred",
                "producer_script": "scripts/run_real_world_utility_eval.ps1",
                "artifact_path": "runs/real_world_utility_eval_latest.json",
            },
        },
    }
    _write_json(path, payload)


def test_release_gate_contract_schema_and_family_ids() -> None:
    repo_root = _repo_root()
    contract_path = repo_root / "configs" / "release_gate_contract.json"
    schema_path = repo_root / "schemas" / "release_gate_contract.schema.json"
    payload = _read_json(contract_path)
    errors = schema_validation.validate_artifact(payload, schema_path)
    assert errors == []

    required_ids = [
        row["id"] for row in payload["strict_release"]["required_reliability_families"]
    ]
    assert required_ids == [
        "compression",
        "compression_roundtrip_generalization",
        "novel_continuity",
        "novel_continuity_long_horizon",
        "myopic_planning_traps",
        "referential_indexing_suite",
        "epistemic_calibration_suite",
        "authority_under_interference",
        "authority_under_interference_hardening",
        "rpa_mode_switch",
        "intent_spec_layer",
        "noise_escalation",
        "implication_coherence",
        "agency_preserving_substitution",
    ]
    compression_row = payload["strict_release"]["required_reliability_families"][0]
    assert compression_row["id"] == "compression"
    assert compression_row.get("canary_policy") == "triage"


def test_release_reliability_matrix_allow_latest_with_existing_artifacts_passes(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root()
    contract_path = tmp_path / "contract_allow_latest.json"
    artifact_path = tmp_path / "novel_continuity_reliability_latest.json"
    out_path = tmp_path / "release_reliability_matrix.json"

    _write_json(
        artifact_path,
        {
            "status": "PASS",
            "failures": [],
            "generated_at_utc": "2026-02-17T00:00:00Z",
        },
    )
    _make_contract(
        contract_path,
        artifact_path=artifact_path,
        freshness_policy="allow_latest",
    )

    script = repo_root / "scripts" / "run_release_reliability_matrix.ps1"
    result = _run_powershell_file(
        script,
        [
            "-ContractPath",
            str(contract_path),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-Out",
            str(out_path),
            "-UseExistingArtifacts",
        ],
    )
    assert result.returncode == 0, result.stderr

    payload = _read_json(out_path)
    assert payload["status"] == "PASS"
    assert payload["coverage"]["required_total"] == 1
    assert payload["coverage"]["produced_total"] == 1
    assert payload["coverage"]["missing_families"] == []
    assert payload["freshness_violations"] == []
    assert payload["families"][0]["id"] == "novel_continuity"
    assert payload["families"][0]["produced_in_this_run"] is False


def test_release_reliability_matrix_family_canary_policy_override_is_reported(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root()
    contract_path = tmp_path / "contract_canary_override.json"
    artifact_path = tmp_path / "compression_reliability_latest.json"
    out_path = tmp_path / "release_reliability_matrix.json"

    _write_json(
        artifact_path,
        {
            "status": "PASS",
            "failures": [],
            "generated_at_utc": "2026-02-17T00:00:00Z",
        },
    )
    _write_json(
        contract_path,
        {
            "contract_id": "release_gate_contract",
            "version": "test",
            "strict_release": {
                "freshness_policy": "allow_latest",
                "canary_policy": "strict",
                "required_reliability_families": [
                    {
                        "id": "compression",
                        "artifact_path": str(artifact_path),
                        "stage": "target",
                        "canary_policy": "triage",
                        "allowed_statuses": ["PASS"],
                    }
                ],
                "utility_gate": {
                    "required": False,
                    "producer_mode": "deferred",
                    "producer_script": "scripts/run_real_world_utility_eval.ps1",
                    "artifact_path": "runs/real_world_utility_eval_latest.json",
                },
            },
        },
    )

    script = repo_root / "scripts" / "run_release_reliability_matrix.ps1"
    result = _run_powershell_file(
        script,
        [
            "-ContractPath",
            str(contract_path),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-Out",
            str(out_path),
            "-UseExistingArtifacts",
        ],
    )
    assert result.returncode == 0, result.stderr

    payload = _read_json(out_path)
    assert payload["status"] == "PASS"
    assert payload["strict_release"]["canary_policy"] == "strict"
    assert payload["families"][0]["id"] == "compression"
    assert payload["families"][0]["canary_policy"] == "triage"


def test_release_reliability_matrix_must_regenerate_with_existing_artifacts_fails(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root()
    contract_path = tmp_path / "contract_must_regenerate.json"
    artifact_path = tmp_path / "novel_continuity_reliability_latest.json"
    out_path = tmp_path / "release_reliability_matrix.json"

    _write_json(
        artifact_path,
        {
            "status": "PASS",
            "failures": [],
            "generated_at_utc": "2026-02-17T00:00:00Z",
        },
    )
    _make_contract(
        contract_path,
        artifact_path=artifact_path,
        freshness_policy="must_regenerate_this_run",
    )

    script = repo_root / "scripts" / "run_release_reliability_matrix.ps1"
    result = _run_powershell_file(
        script,
        [
            "-ContractPath",
            str(contract_path),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-Out",
            str(out_path),
            "-UseExistingArtifacts",
        ],
    )
    assert result.returncode == 0, result.stderr

    payload = _read_json(out_path)
    assert payload["status"] == "FAIL"
    assert payload["freshness_violations"] == ["novel_continuity:not_regenerated_in_this_run"]
    assert any("freshness_violations" in failure for failure in payload["failures"])


def test_release_reliability_matrix_fail_on_matrix_fail_returns_nonzero(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root()
    contract_path = tmp_path / "contract_must_regenerate.json"
    artifact_path = tmp_path / "novel_continuity_reliability_latest.json"
    out_path = tmp_path / "release_reliability_matrix.json"

    _write_json(
        artifact_path,
        {
            "status": "PASS",
            "failures": [],
            "generated_at_utc": "2026-02-17T00:00:00Z",
        },
    )
    _make_contract(
        contract_path,
        artifact_path=artifact_path,
        freshness_policy="must_regenerate_this_run",
    )

    script = repo_root / "scripts" / "run_release_reliability_matrix.ps1"
    result = _run_powershell_file(
        script,
        [
            "-ContractPath",
            str(contract_path),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-Out",
            str(out_path),
            "-UseExistingArtifacts",
            "-FailOnMatrixFail",
        ],
    )
    assert result.returncode != 0
    payload = _read_json(out_path)
    assert payload["status"] == "FAIL"


def test_release_profile_fastlocal_requires_explicit_triage_override() -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_release_check.ps1"
    allowlist_path = repo_root / "configs" / "optional_metric_exemptions_allowlist.json"
    result = _run_powershell_file(
        script,
        [
            "-GateAdapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-GateProfile",
            "release",
            "-FastLocal",
            "-SkipThresholds",
            "-SkipReliabilitySignal",
            "-SkipRealWorldUtilityEval",
            "-OptionalMetricExemptionsAllowlistPath",
            str(allowlist_path),
        ],
    )
    assert result.returncode != 0
    message = f"{result.stdout}\n{result.stderr}"
    assert "GateProfile=release with -FastLocal requires explicit" in message
    assert "AllowReleaseFastLocalTriage" in message


def test_release_check_strict_contract_matrix_to_reliability_wiring(tmp_path: Path) -> None:
    repo_root = _repo_root()
    runs_root = repo_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    fixed_paths = [
        runs_root / "latest_rag_strict",
        runs_root / "rpa_control_latest.json",
        runs_root / "release_gates" / "instruction_override_gate" / "summary.json",
        runs_root / "release_gates" / "instruction_override_gate" / "sweep_status.json",
        runs_root / "release_gates" / "memory_verify_sensitivity.json",
        runs_root / "compression_reliability_latest.json",
        runs_root / "compression_roundtrip_generalization_reliability_latest.json",
        runs_root / "myopic_planning_traps_reliability_latest.json",
        runs_root / "referential_indexing_suite_reliability_latest.json",
        runs_root / "novel_continuity_reliability_latest.json",
        runs_root / "novel_continuity_long_horizon_reliability_latest.json",
        runs_root / "epistemic_calibration_suite_reliability_latest.json",
        runs_root / "authority_under_interference_reliability_latest.json",
        runs_root / "authority_under_interference_hardening_reliability_latest.json",
        runs_root / "rpa_mode_switch_reliability_latest.json",
        runs_root / "intent_spec_layer_reliability_latest.json",
        runs_root / "noise_escalation_reliability_latest.json",
        runs_root / "implication_coherence_reliability_latest.json",
        runs_root / "agency_preserving_substitution_reliability_latest.json",
    ]
    fixed_paths += [repo_root / path for path in _required_ui_baseline_outputs()]
    collisions = [path for path in fixed_paths if path.exists()]
    if collisions:
        pytest.skip("requires clean release fixture paths under runs/ to avoid clobbering local artifacts")

    fixture_root = runs_root / "test_release_fixture_matrix_wiring"
    fixture_root.mkdir(parents=True, exist_ok=True)
    utility_artifact = fixture_root / "real_world_utility_eval_latest.json"
    utility_script = tmp_path / "run_real_world_utility_eval_stub.ps1"
    utility_script.write_text(
        (
            "param([string]$Adapter, [string]$Protocol)\n"
            "$payload = @'\n"
            '{'
            '"status":"PASS",'
            '"comparison":{"clarification_burden_delta":0.0},'
            '"pass_inputs":{"false_commit_improvement":0.1,"correction_improvement":1.0},'
            '"baseline":{"clarification_burden":0.2,"false_commit_rate":0.2,"correction_turns_per_task":2.0},'
            '"controlled":{"clarification_burden":0.2,"false_commit_rate":0.1,"correction_turns_per_task":1.0}'
            "}\n"
            "'@\n"
            f"New-Item -ItemType Directory -Force -Path '{utility_artifact.parent}' | Out-Null\n"
            f"$payload | Set-Content -Path '{utility_artifact}' -Encoding UTF8\n"
            "exit 0\n"
        ),
        encoding="utf-8",
    )

    strict_run = fixture_root / "rag_strict_run"
    strict_run.mkdir(parents=True, exist_ok=True)
    _touch_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    (runs_root / "latest_rag_strict").write_text(str(strict_run), encoding="utf-8")

    _touch_json(
        runs_root / "rpa_control_latest.json",
        {
            "control_contract_version": "0.2",
            "mode": "reason",
            "decision": "ask",
            "confidence": 0.8,
            "risk": 0.2,
            "why": [],
        },
    )

    _touch_json(
        runs_root / "release_gates" / "instruction_override_gate" / "summary.json",
        {
            "status": "PASS",
            "efficiency": {
                "tokens_per_q_mean": 100.0,
                "tokens_per_q_p90": 120.0,
                "wall_s_per_q_mean": 0.1,
                "wall_s_per_q_p90": 0.2,
            },
        },
    )
    _touch_json(
        runs_root / "release_gates" / "instruction_override_gate" / "sweep_status.json",
        {
            "sweep_outcome": "pass",
            "sweep_exit_code": 0,
            "completed_runs": 1,
            "expected_runs": 1,
        },
    )

    _touch_json(
        runs_root / "release_gates" / "memory_verify_sensitivity.json",
        {
            "status": "PASS",
            "coverage": {
                "scenario_count": 18,
                "max_invalid_rate": 1.0,
                "max_actions_blocked": 60,
                "max_total": 100,
                "distinct_tag_count": 5,
                "distinct_reason_count": 9,
            },
            "checks": {
                "monotonic_invalid_rate": True,
                "monotonic_verified_rate": True,
                "blocked_equals_invalid": True,
                "blocked_matches_expected": True,
                "all_used_count_expected": True,
                "invalid_rate_matches_expected": True,
                "verified_rate_matches_expected": True,
                "unused_entries_excluded": True,
                "range_exercised": True,
                "high_scale_exercised": True,
                "tag_reason_diversity": True,
            },
        },
    )

    for ui_path in _required_ui_baseline_outputs():
        _touch_json(repo_root / ui_path, {"status": "PASS"})

    persona_families = {
        "compression_families": runs_root / "compression_reliability_latest.json",
        "compression_roundtrip_generalization": runs_root
        / "compression_roundtrip_generalization_reliability_latest.json",
        "myopic_planning_traps": runs_root / "myopic_planning_traps_reliability_latest.json",
        "referential_indexing_suite": runs_root / "referential_indexing_suite_reliability_latest.json",
        "novel_continuity": runs_root / "novel_continuity_reliability_latest.json",
        "novel_continuity_long_horizon": runs_root / "novel_continuity_long_horizon_reliability_latest.json",
        "epistemic_calibration_suite": runs_root / "epistemic_calibration_suite_reliability_latest.json",
        "authority_under_interference": runs_root / "authority_under_interference_reliability_latest.json",
        "authority_under_interference_hardening": runs_root
        / "authority_under_interference_hardening_reliability_latest.json",
        "rpa_mode_switch": runs_root / "rpa_mode_switch_reliability_latest.json",
        "intent_spec_layer": runs_root / "intent_spec_layer_reliability_latest.json",
        "noise_escalation": runs_root / "noise_escalation_reliability_latest.json",
        "implication_coherence": runs_root / "implication_coherence_reliability_latest.json",
        "agency_preserving_substitution": runs_root
        / "agency_preserving_substitution_reliability_latest.json",
    }

    for family, reliability_path in persona_families.items():
        run_dir = fixture_root / f"{family}_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        if family == "compression_families":
            _touch_json(
                run_dir / "compression_families_summary.json",
                {
                    "benchmark": "compression_families",
                    "families": {
                        "compression_loss_bounded": {
                            "persona_invariance": {
                                "row_invariance_rate": 1.0,
                                "rows_total": 4,
                                "rows_changed": 0,
                            }
                        },
                        "compression_recoverability": {
                            "persona_invariance": {
                                "row_invariance_rate": 1.0,
                                "rows_total": 4,
                                "rows_changed": 0,
                            }
                        },
                    },
                },
            )
        else:
            _touch_json(
                run_dir / f"{family}_summary.json",
                {
                    "benchmark": family,
                    "persona_invariance": {
                        "row_invariance_rate": 1.0,
                        "rows_total": 4,
                        "rows_changed": 0,
                    },
                    "holdout": {"means": {"value_acc": 1.0}},
                },
            )
        _touch_json(
            reliability_path,
            {
                "benchmark": f"{family}_reliability",
                "status": "PASS",
                "runs": [str(run_dir)],
                "failures": [],
                "generated_at_utc": "2026-02-17T00:00:00Z",
            },
        )

    contract_path = tmp_path / "release_contract_allow_latest.json"
    _write_json(
        contract_path,
        {
            "contract_id": "release_gate_contract",
            "version": "test-release-wiring",
            "strict_release": {
                "freshness_policy": "allow_latest",
                "canary_policy": "strict",
                "required_reliability_families": [
                    {
                        "id": "compression",
                        "artifact_path": "runs/compression_reliability_latest.json",
                        "stage": "target",
                        "allowed_statuses": ["PASS"],
                    },
                    {
                        "id": "novel_continuity",
                        "artifact_path": "runs/novel_continuity_reliability_latest.json",
                        "stage": "target",
                        "allowed_statuses": ["PASS"],
                    },
                    {
                        "id": "authority_under_interference",
                        "artifact_path": "runs/authority_under_interference_reliability_latest.json",
                        "stage": "target",
                        "allowed_statuses": ["PASS"],
                    },
                ],
                "utility_gate": {
                    "required": True,
                    "producer_mode": "script",
                    "producer_script": str(utility_script),
                    "artifact_path": str(utility_artifact),
                },
            },
        },
    )

    script = repo_root / "scripts" / "run_release_check.ps1"
    allowlist_path = repo_root / "configs" / "optional_metric_exemptions_allowlist.json"
    result = _run_powershell_file(
        script,
        [
            "-GateAdapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-GateProfile",
            "release",
            "-FastLocal",
            "-AllowReleaseFastLocalTriage",
            "-ReleaseGateContractPath",
            str(contract_path),
            "-SkipThresholds",
            "-SkipRequireControlFamilies",
            "-SkipDerivedScoreFloors",
            "-SkipVariants",
            "-OptionalMetricExemptionsAllowlistPath",
            str(allowlist_path),
        ],
    )
    assert result.returncode == 0, result.stderr

    latest_release = (runs_root / "latest_release").read_text(encoding="utf-8-sig").strip()
    matrix_path = Path(latest_release) / "release_reliability_matrix.json"
    assert matrix_path.exists()
    matrix_payload = _read_json(matrix_path)
    assert matrix_payload["status"] == "PASS"
    assert matrix_payload["coverage"]["required_total"] == 3
    assert matrix_payload["coverage"]["produced_total"] == 3
    assert matrix_payload["coverage"]["missing_families"] == []
    assert matrix_payload["failing_families"] == []
    assert matrix_payload["strict_release"]["use_existing_artifacts"] is True

    assert utility_artifact.exists()
    utility_payload = _read_json(utility_artifact)
    assert utility_payload["status"] == "PASS"

    reliability_signal_path = runs_root / "reliability_signal_latest.json"
    assert reliability_signal_path.exists()
    reliability_signal = _read_json(reliability_signal_path)
    assert reliability_signal["status"] == "PASS"
