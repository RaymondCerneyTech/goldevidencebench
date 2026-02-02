from __future__ import annotations

import pytest

from goldevidencebench.baselines import parse_book_ledger
from goldevidencebench.adapters.ledger_adapter import create_adapter
from goldevidencebench.adapters.log_to_book_adapter import LogToBookAdapter
from goldevidencebench.generate import EpisodeConfig, generate_dataset
from goldevidencebench.model_runner import run_adapter, validate_adapter_output


def test_adapter_closed_book_receives_no_document() -> None:
    cfg = EpisodeConfig(steps=12, keys=3, queries=3, twins=False, distractor_profile="standard")
    data = generate_dataset(seed=1, episodes=1, cfg=cfg)
    adapter = create_adapter()

    preds = run_adapter(data_rows=data, adapter=adapter, protocol="closed_book")
    assert preds.tokens > 0
    for row in data:
        assert row["document"]  # original has doc
    # if adapter leaked doc, validate would have failed due to closed_book guard in predict_ledger_row
    assert len(preds.predictions) == len(data)


def test_adapter_output_validation_rejects_bad_support_ids() -> None:
    cfg = EpisodeConfig(steps=6, keys=2, queries=2, twins=False, distractor_profile="standard")
    data = generate_dataset(seed=2, episodes=1, cfg=cfg)
    row = data[0]

    with pytest.raises(ValueError):
        validate_adapter_output(row=row, raw={"value": "foo", "support_ids": ["UBADBAD"]}, protocol="open_book", max_support_k=3)


def test_adapter_output_validation_rejects_missing_value() -> None:
    cfg = EpisodeConfig(steps=6, keys=2, queries=2, twins=False, distractor_profile="standard")
    data = generate_dataset(seed=3, episodes=1, cfg=cfg)
    row = data[0]

    with pytest.raises(ValueError):
        validate_adapter_output(row=row, raw={"support_ids": []}, protocol="open_book", max_support_k=3)


def test_adapter_output_validation_ignores_debug_output_field() -> None:
    cfg = EpisodeConfig(steps=6, keys=2, queries=2, twins=False, distractor_profile="standard")
    data = generate_dataset(seed=5, episodes=1, cfg=cfg)
    row = data[0]

    parsed = validate_adapter_output(
        row=row,
        raw={"value": "foo", "support_ids": [], "output": "{\"value\": \"foo\"}"},
        protocol="open_book",
        max_support_k=3,
    )
    assert parsed == {"value": "foo", "support_ids": []}


def test_adapter_output_coerces_numeric_value() -> None:
    cfg = EpisodeConfig(steps=6, keys=2, queries=2, twins=False, distractor_profile="standard")
    row = generate_dataset(seed=13, episodes=1, cfg=cfg)[0]
    parsed = validate_adapter_output(
        row=row,
        raw={"value": 2887, "support_ids": []},
        protocol="open_book",
        max_support_k=3,
    )
    assert parsed == {"value": "2887", "support_ids": []}


def test_adapter_output_validation_accepts_doc_id_supports() -> None:
    cfg = EpisodeConfig(steps=6, keys=2, queries=2, twins=False, distractor_profile="standard")
    row = generate_dataset(seed=9, episodes=1, cfg=cfg)[0]
    row["meta"] = {**row.get("meta", {}), "citation_mode": "doc_id", "doc_ids": ["DOC1", "DOC2"]}
    parsed = validate_adapter_output(
        row=row,
        raw={"value": "foo", "support_ids": ["DOC1"]},
        protocol="open_book",
        max_support_k=3,
    )
    assert parsed == {"value": "foo", "support_ids": ["DOC1"]}


def test_adapter_output_validation_closed_book_uses_book_ids() -> None:
    cfg = EpisodeConfig(steps=6, keys=2, queries=2, twins=False, distractor_profile="standard")
    row = generate_dataset(seed=11, episodes=1, cfg=cfg)[0]
    book_ids = parse_book_ledger(row["book"])
    assert book_ids
    book_uid = book_ids[0]["uid"]
    # Force a mismatched document so open-book validation would fail.
    row["document"] = "## Episode Log\n- [UAAAAAA] UPDATE step=1 SET tag.00 = bogus"

    parsed = validate_adapter_output(
        row=row,
        raw={"value": "foo", "support_ids": [book_uid]},
        protocol="closed_book",
        max_support_k=3,
    )
    assert parsed == {"value": "foo", "support_ids": [book_uid]}


def test_build_artifact_adapter_runs_closed_book() -> None:
    cfg = EpisodeConfig(steps=12, keys=3, queries=3, twins=False, distractor_profile="standard")
    data = generate_dataset(seed=4, episodes=1, cfg=cfg)
    adapter = LogToBookAdapter()
    res = run_adapter(data_rows=data, adapter=adapter, protocol="closed_book")
    assert len(res.predictions) == len(data)
