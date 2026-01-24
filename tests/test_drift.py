from pathlib import Path

import pytest

from goldevidencebench import drift as drift_mod
from goldevidencebench import walls


def _row(rid: str, key: str, q_index: int, gold_value: str) -> dict:
    return {
        "id": rid,
        "episode_id": "E1",
        "gold": {"value": gold_value},
        "meta": {"key": key, "q_index": q_index},
    }


def test_compute_drift_counts_persistence():
    data_rows = [
        _row("q1", "tag.01", 1, "A"),
        _row("q2", "tag.01", 2, "B"),
        _row("q3", "tag.01", 3, "C"),
    ]
    pred_by_id = {
        "q1": {"value": "X"},
        "q2": {"value": "X"},
        "q3": {"value": "C"},
    }
    retrieval_by_id = {
        rid: {"correct_included": True, "dropped_correct": False, "gold_missing": False}
        for rid in ("q1", "q2", "q3")
    }
    counts = drift_mod.compute_drift_counts(
        data_rows=data_rows, pred_by_id=pred_by_id, retrieval_by_id=retrieval_by_id
    )
    metrics = counts.as_metrics()
    assert metrics["step_rate"] == pytest.approx(2 / 3)
    assert metrics["persistence_rate"] == pytest.approx(1 / 3)
    assert metrics["wrong_commit_rate"] == pytest.approx(2 / 3)
    assert metrics["run_rate"] == 1.0


def test_find_drift_wall():
    points = [
        walls.WallPoint(run_dir=Path("r1"), param=80, metric=0.02, state_mode=None, distractor_profile=None),
        walls.WallPoint(run_dir=Path("r2"), param=120, metric=0.08, state_mode=None, distractor_profile=None),
        walls.WallPoint(run_dir=Path("r3"), param=160, metric=0.12, state_mode=None, distractor_profile=None),
    ]
    last_ok, wall = drift_mod.find_drift_wall(points, threshold=0.1, direction="gte")
    assert last_ok is not None
    assert wall is not None
    assert last_ok.param == 120
    assert wall.param == 160
