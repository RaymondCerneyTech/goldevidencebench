from __future__ import annotations

from goldevidencebench.baselines import parse_updates
from goldevidencebench.generate import EpisodeConfig, generate_dataset


def test_generate_ledger_has_steps_and_support_ids_match() -> None:
    cfg = EpisodeConfig(
        steps=50,
        keys=6,
        queries=10,
        derived_query_rate=0.0,
        chapters=3,
        distractor_rate=0.3,
        clear_rate=0.1,
        twins=False,
        distractor_profile="standard",
        state_mode="kv",
    )
    rows = generate_dataset(seed=123, episodes=1, cfg=cfg)
    assert len(rows) == cfg.queries

    doc = rows[0]["document"]
    updates = parse_updates(doc)
    assert len(updates) == cfg.steps

    for row in rows:
        key = row["meta"]["key"]
        gold = row["gold"]
        last_uid = None
        last_value = None
        for e in updates:
            if e["key"] == key:
                last_uid = e["uid"]
                last_value = e["value"]

        assert gold["support_id"] == last_uid
        assert gold["value"] == last_value


def test_tail_distractor_steps_reduce_updates() -> None:
    cfg = EpisodeConfig(
        steps=20,
        keys=4,
        queries=6,
        derived_query_rate=0.0,
        chapters=2,
        distractor_rate=0.2,
        tail_distractor_steps=5,
        clear_rate=0.05,
        twins=False,
        distractor_profile="standard",
        state_mode="kv",
    )
    rows = generate_dataset(seed=99, episodes=1, cfg=cfg)
    assert len(rows) == cfg.queries

    updates = parse_updates(rows[0]["document"])
    assert len(updates) == cfg.steps - cfg.tail_distractor_steps

    for row in rows:
        tokens_since = row["meta"].get("tokens_since_update")
        assert tokens_since is not None
        assert tokens_since > 0
