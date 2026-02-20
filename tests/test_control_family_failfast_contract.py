from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_run_control_family_scaffold_supports_failfast_score_mode() -> None:
    script = (_repo_root() / "scripts" / "run_control_family_scaffold.ps1").read_text(encoding="utf-8")

    assert "[switch]$FailFast" in script
    assert "function Invoke-PythonScore" in script
    assert "if ($FailFast) {" in script
    assert "Invoke-PythonChecked -StepName $StepName -CommandArgs $CommandArgs" in script
    assert "Invoke-PythonSoftFail -StepName $StepName -CommandArgs $CommandArgs" in script
    assert 'Invoke-PythonScore -StepName "score_anchors"' in script
    assert 'Invoke-PythonScore -StepName "score_holdout"' in script
    assert 'Invoke-PythonScore -StepName "score_canary"' in script


def test_run_implication_family_forwards_failfast_to_scaffold() -> None:
    script = (_repo_root() / "scripts" / "run_implication_coherence_family.ps1").read_text(encoding="utf-8")

    assert "[switch]$FailFast" in script
    assert "-FailFast:$FailFast" in script


def test_run_agency_family_forwards_failfast_to_scaffold() -> None:
    script = (_repo_root() / "scripts" / "run_agency_preserving_substitution_family.ps1").read_text(encoding="utf-8")

    assert "[switch]$FailFast" in script
    assert "-FailFast:$FailFast" in script


def test_run_authority_family_supports_failfast_score_mode() -> None:
    script = (_repo_root() / "scripts" / "run_authority_under_interference_family.ps1").read_text(encoding="utf-8")

    assert "[switch]$FailFast" in script
    assert "function Invoke-PythonScore" in script
    assert "if ($FailFast) {" in script
    assert "Invoke-PythonChecked -StepName $StepName -CommandArgs $CommandArgs" in script
    assert "Invoke-PythonSoftFail -StepName $StepName -CommandArgs $CommandArgs" in script
    assert 'Invoke-PythonScore -StepName "score_anchors"' in script
    assert 'Invoke-PythonScore -StepName "score_holdout"' in script
    assert 'Invoke-PythonScore -StepName "score_canary"' in script


def test_run_intent_spec_family_forwards_failfast_to_scaffold() -> None:
    script = (_repo_root() / "scripts" / "run_intent_spec_family.ps1").read_text(encoding="utf-8")

    assert "[switch]$FailFast" in script
    assert "-FailFast:$FailFast" in script


def test_run_control_family_scaffold_clamps_implication_anchor_hard_case_floor() -> None:
    script = (_repo_root() / "scripts" / "run_control_family_scaffold.ps1").read_text(encoding="utf-8")

    assert "function Get-HardCaseCount" in script
    assert "function Set-ArgValue" in script
    assert '$anchorsThresholdArgs = @($thresholdArgs)' in script
    assert 'if ($Family -eq "implication_coherence") {' in script
    assert 'Set-ArgValue -Args $anchorsThresholdArgs -Name "--min-hard-case-count"' in script
    assert "$anchorsScoreArgs += $anchorsThresholdArgs" in script


def test_run_family_stage_triplet_registers_social_pressure_self_doubt_family() -> None:
    script = (_repo_root() / "scripts" / "run_family_stage_triplet.ps1").read_text(encoding="utf-8")

    assert '"social_pressure_self_doubt"' in script
    assert '".\\scripts\\run_social_pressure_self_doubt_family.ps1"' in script
    assert '".\\scripts\\check_social_pressure_self_doubt_reliability.py"' in script
    assert '"runs\\social_pressure_self_doubt_reliability_latest.json"' in script
