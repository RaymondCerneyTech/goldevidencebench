from __future__ import annotations

from goldevidencebench.adapters.streaming_llama_cpp_adapter import build_streaming_book, StreamingConfig
from goldevidencebench.baselines import parse_book_ledger, parse_updates
from goldevidencebench.generate import EpisodeConfig, generate_dataset


def test_streaming_builder_keeps_latest_per_key() -> None:
    cfg = EpisodeConfig(
        steps=40,
        keys=6,
        queries=6,
        derived_query_rate=0.0,
        chapters=3,
        distractor_rate=0.4,
        clear_rate=0.1,
        twins=False,
        distractor_profile="standard",
        state_mode="kv",
    )
    rows = generate_dataset(seed=42, episodes=1, cfg=cfg)
    doc = rows[0]["document"]

    updates = parse_updates(doc)
    last_by_key = {}
    for u in updates:
        last_by_key[u["key"]] = u

    artifact = build_streaming_book(
        document=doc,
        episode_id="E0001",
        cfg=StreamingConfig(chunk_tokens=50),
    )
    ledger = parse_book_ledger(artifact)

    assert len(ledger) == len(last_by_key)
    seen_keys = {entry["key"] for entry in ledger}
    assert seen_keys == set(last_by_key.keys())
    for entry in ledger:
        last = last_by_key[entry["key"]]
        assert entry["uid"] == last["uid"]
        assert entry["step"] == last["step"]
        assert entry["op"] == last["op"]
        assert entry["value"] == last["value"]
