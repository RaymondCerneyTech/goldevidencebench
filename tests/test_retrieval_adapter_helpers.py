from __future__ import annotations

import random

from goldevidencebench.adapters.retrieval_llama_cpp_adapter import (
    _apply_drop_with_rng,
    _apply_order,
    _build_min_book,
    _latest_entry_for_key,
    _rerank_latest_step,
    _select_entries_for_key,
)
from goldevidencebench.baselines import parse_book_ledger
from goldevidencebench.generate import EpisodeConfig, generate_dataset


def test_latest_entry_for_key_picks_last_step() -> None:
    cfg = EpisodeConfig(
        steps=25,
        keys=4,
        queries=4,
        derived_query_rate=0.0,
        chapters=2,
        distractor_rate=0.3,
        clear_rate=0.1,
        twins=False,
        distractor_profile="standard",
        state_mode="kv",
    )
    rows = generate_dataset(seed=10, episodes=1, cfg=cfg)
    book = rows[0]["book"]
    key = rows[0]["meta"]["key"]
    entry = _latest_entry_for_key(book, key)
    assert entry is not None
    for other in parse_book_ledger(book):
        if other["key"] == key:
            assert entry["step"] >= other["step"]


def test_build_min_book_contains_single_entry() -> None:
    cfg = EpisodeConfig(steps=10, keys=3, queries=3, twins=False, distractor_profile="standard")
    rows = generate_dataset(seed=2, episodes=1, cfg=cfg)
    book = rows[0]["book"]
    key = rows[0]["meta"]["key"]
    entry = _latest_entry_for_key(book, key)
    assert entry is not None
    mini = _build_min_book(entry=entry, key=key, episode_id="E0001")
    ledger = parse_book_ledger(mini)
    assert len(ledger) == 1
    assert ledger[0]["uid"] == entry["uid"]


def test_select_entries_for_key_with_wrong_line() -> None:
    cfg = EpisodeConfig(steps=20, keys=3, queries=3, twins=False, distractor_profile="standard")
    rows = generate_dataset(seed=3, episodes=1, cfg=cfg)
    book = rows[0]["book"]
    key = rows[0]["meta"]["key"]
    entries = parse_book_ledger(book)
    selected, diag, _wrong = _select_entries_for_key(entries=entries, key=key, k=1, wrong_type="other_key")
    assert selected
    assert diag["selected_count"] == len(selected)
    assert diag["correct_included"] in {True, False}


def test_apply_drop_with_rng_removes_correct() -> None:
    selected = [{"uid": "U000001"}, {"uid": "U000002"}]
    wrong = {"uid": "U000099"}
    rng = random.Random(123)
    dropped, did_drop = _apply_drop_with_rng(
        selected=selected,
        correct_uid="U000001",
        wrong_entry=wrong,
        drop_prob=1.0,
        rng=rng,
    )
    assert did_drop is True
    assert all(e["uid"] != "U000001" for e in dropped)


def test_order_gold_last_moves_correct_to_end() -> None:
    selected = [{"uid": "U000001"}, {"uid": "U000002"}, {"uid": "U000003"}]
    ordered, applied = _apply_order(selected=selected, correct_uid="U000002", order="gold_last")
    assert applied == "gold_last"
    assert ordered[-1]["uid"] == "U000002"


def test_order_gold_middle_inserts_in_center() -> None:
    selected = [
        {"uid": "U000001"},
        {"uid": "U000002"},
        {"uid": "U000003"},
        {"uid": "U000004"},
        {"uid": "U000005"},
    ]
    ordered, applied = _apply_order(selected=selected, correct_uid="U000003", order="gold_middle")
    assert applied == "gold_middle"
    assert ordered[len(ordered) // 2]["uid"] == "U000003"


def test_rerank_latest_step_picks_max_step() -> None:
    entries = [
        {"uid": "U000001", "step": 2},
        {"uid": "U000002", "step": 10},
        {"uid": "U000003", "step": 5},
    ]
    chosen = _rerank_latest_step(entries)
    assert chosen is not None
    assert chosen["uid"] == "U000002"
