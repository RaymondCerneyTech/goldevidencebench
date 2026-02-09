from __future__ import annotations

from goldevidencebench.adapters.llm_book_builder_adapter import (
    build_book_from_updates,
    build_book_per_key_deterministic,
)
from goldevidencebench.baselines import parse_book_ledger, parse_updates
from goldevidencebench.generate import EpisodeConfig, generate_dataset


def test_builder_helpers_match_latest_updates() -> None:
    cfg = EpisodeConfig(
        steps=30,
        keys=5,
        queries=5,
        derived_query_rate=0.0,
        chapters=2,
        distractor_rate=0.4,
        clear_rate=0.1,
        twins=False,
        distractor_profile="standard",
        state_mode="kv",
    )
    rows = generate_dataset(seed=7, episodes=1, cfg=cfg)
    doc = rows[0]["document"]
    updates = parse_updates(doc)
    last_by_key = {}
    for upd in updates:
        last_by_key[upd["key"]] = upd

    book_full = build_book_from_updates(document=doc, episode_id="E0001")
    book_per_key = build_book_per_key_deterministic(document=doc, episode_id="E0001")

    ledger_full = parse_book_ledger(book_full)
    ledger_per_key = parse_book_ledger(book_per_key)
    assert {e["key"] for e in ledger_full} == set(last_by_key.keys())
    assert {e["key"] for e in ledger_per_key} == set(last_by_key.keys())
    for entry in ledger_per_key:
        last = last_by_key[entry["key"]]
        assert entry["uid"] == last["uid"]
        assert entry["step"] == last["step"]
        assert entry["op"] == last["op"]
        assert entry["value"] == last["value"]


def test_parse_book_ledger_supports_generic_keys() -> None:
    book = """# Example

## State Ledger
- [UABC123] step=1 SET policy.cache_ttl_minutes = 60
- [UDEF456] step=2 NOTE policy.cache_ttl_minutes = 15
- [U13579B] step=3 SET policy.cache_ttl_minutes = 120
"""
    entries = parse_book_ledger(book)
    assert len(entries) == 3
    assert entries[-1]["key"] == "policy.cache_ttl_minutes"
    assert entries[-1]["op"] == "SET"
    assert entries[-1]["value"] == "120"


def test_parse_updates_supports_generic_keys() -> None:
    document = """# Episode

## Episode Log
- [UABC123] UPDATE step=1 SET policy.export_window_days = 30
- [UDEF456] UPDATE step=2 NOTE policy.export_window_days = 21
- [U13579B] UPDATE step=3 CLEAR policy.export_window_days
"""
    updates = parse_updates(document)
    assert len(updates) == 3
    assert updates[0]["key"] == "policy.export_window_days"
    assert updates[1]["op"] == "NOTE"
    assert updates[2]["op"] == "CLEAR"
