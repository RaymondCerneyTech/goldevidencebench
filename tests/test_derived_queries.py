from __future__ import annotations

from goldevidencebench.baselines import iter_predictions
from goldevidencebench.generate import EpisodeConfig, generate_dataset
from goldevidencebench.grade import grade_rows


def test_set_mode_derived_queries_are_scored() -> None:
    cfg = EpisodeConfig(
        steps=25,
        keys=4,
        queries=6,
        derived_query_rate=1.0,
        state_mode="set",
        twins=False,
        distractor_profile="standard",
    )
    rows = generate_dataset(seed=77, episodes=1, cfg=cfg)
    assert any(r["meta"].get("query_type") == "derived" for r in rows)

    preds = list(iter_predictions(rows, baseline="ledger", protocol="open_book"))
    res = grade_rows(data_rows=rows, pred_by_id={p["id"]: p for p in preds}, citations="auto")
    assert res.exact_acc == 1.0
