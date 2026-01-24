from __future__ import annotations

from goldevidencebench.adapters.mock_adapter import create_adapter
from goldevidencebench.generate import EpisodeConfig, generate_dataset
from goldevidencebench.model_runner import run_adapter


def test_mock_adapter_returns_gold() -> None:
    cfg = EpisodeConfig(steps=8, keys=3, queries=3, twins=False, distractor_profile="standard")
    rows = generate_dataset(seed=7, episodes=1, cfg=cfg)
    adapter = create_adapter()
    res = run_adapter(data_rows=rows, adapter=adapter, protocol="open_book")

    assert len(res.predictions) == len(rows)
    pred_by_id = {row["id"]: row for row in res.predictions}
    for row in rows:
        pred = pred_by_id[row["id"]]
        assert pred["value"] == row["gold"]["value"]
