from __future__ import annotations

import json
from pathlib import Path

from goldevidencebench.rpa_reason_codes import ReasonCode
from goldevidencebench.rpa_runtime_policy import evaluate_runtime_policy


def _reason_codes(policy) -> set[str]:
    return {reason.code for reason in policy.reasons}


def test_runtime_policy_unauthorized_substitution_blocks() -> None:
    policy = evaluate_runtime_policy(
        {
            "confidence": 0.95,
            "risk": 0.05,
            "horizon_depth": 1,
            "needed_info": [],
            "reversibility": "reversible",
        },
        {
            "reversibility": "reversible",
            "substitution": {
                "requested_option": "A",
                "proposed_option": "B",
                "disclosed": False,
                "authorized": False,
                "recoverable": False,
            },
        },
    )

    assert policy.blocked is True
    assert policy.mode == "reason"
    assert policy.decision == "ask"
    assert ReasonCode.UNAUTHORIZED_SUBSTITUTION.value in _reason_codes(policy)


def test_runtime_policy_ic_block_downgrades_decision() -> None:
    policy = evaluate_runtime_policy(
        {
            "confidence": 0.90,
            "risk": 0.10,
            "horizon_depth": 2,
            "needed_info": [],
            "reversibility": "reversible",
        },
        {
            "reversibility": "reversible",
            "ic_score": 0.60,
            "implication_break_rate": 0.20,
        },
    )

    assert policy.blocked is True
    assert policy.mode == "reason"
    assert policy.decision == "retrieve"
    codes = _reason_codes(policy)
    assert ReasonCode.LOW_IC.value in codes
    assert ReasonCode.HIGH_IMPLICATION_BREAK.value in codes


def test_runtime_policy_irreversible_guard_requires_verify() -> None:
    policy = evaluate_runtime_policy(
        {
            "confidence": 0.70,
            "risk": 0.30,
            "horizon_depth": 1,
            "needed_info": [],
            "reversibility": "irreversible",
        },
        {
            "reversibility": "irreversible",
            "ic_score": 0.79,
            "contradiction_repair_rate": 0.70,
            "intent_preservation_score": 0.80,
        },
    )

    assert policy.blocked is True
    assert policy.mode == "plan"
    assert policy.decision == "verify"
    codes = _reason_codes(policy)
    assert ReasonCode.LOW_CONFIDENCE.value in codes
    assert ReasonCode.HIGH_RISK.value in codes


def test_runtime_policy_unauthorized_substitution_fixture_hard_block() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "runtime_policy_unauthorized_substitution_block.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    snapshot = fixture["snapshot"]
    context = fixture["context"]
    expected = fixture["expected"]

    policy = evaluate_runtime_policy(snapshot, context)

    assert policy.blocked is expected["blocked"]
    assert policy.mode == expected["mode"]
    assert policy.decision == expected["decision"]
    assert expected["reason_code"] in _reason_codes(policy)
