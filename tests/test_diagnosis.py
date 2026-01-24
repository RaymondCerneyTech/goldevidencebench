import pytest

from goldevidencebench import diagnosis as diag
from goldevidencebench.baselines import parse_book_ledger
from goldevidencebench.generate import EpisodeConfig, generate_episode


def test_classifier_priority_order():
    thresholds = diag.DEFAULT_THRESHOLDS.copy()
    metrics = {
        "unsafe_commit_rate": thresholds["unsafe_commit_rate"] + 0.01,
        "flip_rate": thresholds["flip_rate"] + 0.01,
        "gold_present_rate": thresholds["gold_present_rate"] - 0.1,
        "selection_rate_given_present": thresholds["selection_rate_given_present"] - 0.1,
        "authority_violation_rate": thresholds["authority_violation_rate"] + 0.01,
        "answer_correct_given_selected": thresholds["answer_correct_given_selected"] - 0.1,
    }
    assert diag.classify_bottleneck(metrics, thresholds) == "action_safety"

    metrics["unsafe_commit_rate"] = thresholds["unsafe_commit_rate"] - 0.01
    assert diag.classify_bottleneck(metrics, thresholds) == "instability"

    metrics["flip_rate"] = thresholds["flip_rate"] - 0.01
    assert diag.classify_bottleneck(metrics, thresholds) == "retrieval"

    metrics["gold_present_rate"] = thresholds["gold_present_rate"] + 0.01
    assert diag.classify_bottleneck(metrics, thresholds) == "selection"

    metrics["selection_rate_given_present"] = thresholds["selection_rate_given_present"] + 0.01
    assert diag.classify_bottleneck(metrics, thresholds) == "authority"

    metrics["authority_violation_rate"] = thresholds["authority_violation_rate"] - 0.01
    assert diag.classify_bottleneck(metrics, thresholds) == "answering"

    metrics["answer_correct_given_selected"] = thresholds["answer_correct_given_selected"] + 0.01
    assert diag.classify_bottleneck(metrics, thresholds) == "pass"


def test_ladder_selection_ordering():
    summary = {
        "retrieval": {
            "gold_present_rate": 0.95,
            "selection_rate": 0.5,
            "wrong_update_rate": 0.0,
        }
    }
    diagnosis = diag.build_diagnosis(summary=summary)
    assert diagnosis["primary_bottleneck"] == "selection"
    assert diagnosis["prescription"]["title"] == "Improve selection scoring (disambiguation)"
    assert diagnosis["second_best_prescription"]["title"] == "Distill top decoy into a tiny gate"


def test_safety_override():
    summary = {
        "retrieval": {
            "gold_present_rate": 0.2,
            "selection_rate": 0.2,
            "wrong_update_rate": diag.DEFAULT_THRESHOLDS["unsafe_commit_rate"] + 0.05,
        }
    }
    diagnosis = diag.build_diagnosis(summary=summary)
    assert diagnosis["primary_bottleneck"] == "action_safety"
    assert diagnosis["prescription"]["title"] == "Tighten safety gate for unsafe commits"


def test_drift_pass_is_gate_consistent():
    thresholds = diag.DEFAULT_THRESHOLDS.copy()
    summary = {
        "drift": {"step_rate": thresholds["drift_step_rate_max"] - 0.01},
        "retrieval": {
            "gold_present_rate": 0.2,
            "selection_rate": 0.1,
            "selected_note_rate": 0.0,
            "wrong_update_rate": 0.0,
        },
        "by_group": [{"distractor_profile": "stale_tab_state"}],
    }
    diagnosis = diag.build_diagnosis(summary=summary, thresholds=thresholds)
    assert diagnosis["status"] == "PASS"


def test_stale_tab_state_failure_prescription():
    thresholds = diag.DEFAULT_THRESHOLDS.copy()
    summary = {
        "drift": {"step_rate": thresholds["drift_step_rate_max"] + 0.2},
        "retrieval": {
            "selected_note_rate": thresholds["authority_violation_rate"] + 0.5,
            "wrong_update_rate": 0.0,
        },
        "by_group": [{"distractor_profile": "stale_tab_state"}],
    }
    diagnosis = diag.build_diagnosis(summary=summary, thresholds=thresholds)
    assert diagnosis["primary_bottleneck"] == "authority"
    assert diagnosis["prescription"]["title"].startswith("Enable authority filter")
    assert diagnosis["second_best_prescription"]["title"].startswith("Use prefer_set_latest")


def test_focus_drift_failure_prescription():
    thresholds = diag.DEFAULT_THRESHOLDS.copy()
    summary = {
        "drift": {"step_rate": thresholds["drift_step_rate_max"] + 0.2},
        "retrieval": {
            "selected_note_rate": 0.0,
            "wrong_update_rate": 0.0,
        },
        "by_group": [{"distractor_profile": "focus_drift"}],
    }
    diagnosis = diag.build_diagnosis(summary=summary, thresholds=thresholds)
    assert diagnosis["primary_bottleneck"] == "selection"
    assert "focus guard" in diagnosis["prescription"]["title"].lower()


def test_drift_examples_populated():
    cfg = EpisodeConfig(
        steps=6,
        keys=2,
        queries=6,
        derived_query_rate=0.0,
        distractor_rate=0.0,
        tail_distractor_steps=0,
        clear_rate=0.0,
        chapters=1,
        require_citations=True,
        twins=False,
        distractor_profile="stale_tab_state",
        state_mode="kv_commentary",
        note_rate=0.0,
    )
    ep = generate_episode(seed=21, episode_id="E0201", cfg=cfg)
    rows = ep["rows"]
    entries = parse_book_ledger(rows[0]["book"])
    latest_by_key: dict[str, dict[str, str | int | None]] = {}
    for entry in entries:
        key = entry["key"]
        step = int(entry["step"])
        if key not in latest_by_key or step > latest_by_key[key]["step"]:
            latest_by_key[key] = {
                "uid": entry["uid"],
                "op": entry["op"],
                "value": entry.get("value"),
                "step": step,
            }
    pred_by_id: dict[str, dict[str, str | None]] = {}
    retrieval_by_id: dict[str, dict[str, str | bool | None]] = {}
    for row in rows:
        key = row["meta"]["key"]
        chosen = latest_by_key[key]
        value = None if str(chosen["op"]).upper() == "CLEAR" else chosen.get("value")
        pred_by_id[row["id"]] = {"value": value}
        support_ids = row.get("gold", {}).get("support_ids") or []
        correct_uid = support_ids[0] if support_ids else row.get("gold", {}).get("support_id")
        retrieval_by_id[row["id"]] = {
            "correct_included": True,
            "dropped_correct": False,
            "gold_missing": False,
            "selected_uid": chosen["uid"],
            "correct_uid": correct_uid,
        }
    examples = diag.build_drift_examples(
        data_rows=rows,
        pred_by_id=pred_by_id,
        retrieval_by_id=retrieval_by_id,
        holdout_name="stale_tab_state",
    )
    assert examples
    assert examples[0]["why_type"] == "commit_state"
