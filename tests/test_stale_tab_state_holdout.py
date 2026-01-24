from __future__ import annotations

from goldevidencebench import drift as drift_mod
from goldevidencebench.baselines import parse_book_ledger
from goldevidencebench.generate import EpisodeConfig, generate_episode


def _make_cfg() -> EpisodeConfig:
    return EpisodeConfig(
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


def _make_focus_cfg() -> EpisodeConfig:
    return EpisodeConfig(
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
        distractor_profile="focus_drift",
        state_mode="kv_commentary",
        note_rate=0.0,
    )


def test_stale_tab_state_has_newer_note():
    cfg = _make_cfg()
    ep = generate_episode(seed=7, episode_id="E0001", cfg=cfg)
    rows = ep["rows"]
    book = rows[0]["book"]
    entries = parse_book_ledger(book)
    assert entries

    by_key: dict[str, dict[str, list[int]]] = {}
    for e in entries:
        key = e["key"]
        by_key.setdefault(key, {"SET": [], "NOTE": []})
        by_key[key][e["op"]].append(int(e["step"]))

    for key, steps in by_key.items():
        assert steps["SET"], f"missing SET for {key}"
        assert steps["NOTE"], f"missing NOTE for {key}"
        assert max(steps["NOTE"]) > max(steps["SET"]), f"NOTE not newer for {key}"


def test_stale_tab_state_drift_accumulates():
    cfg = _make_cfg()
    ep = generate_episode(seed=11, episode_id="E0002", cfg=cfg)
    rows = ep["rows"]
    book = rows[0]["book"]
    entries = parse_book_ledger(book)
    assert entries

    latest_by_key: dict[str, dict[str, str | None]] = {}
    for e in entries:
        key = e["key"]
        step = int(e["step"])
        if key not in latest_by_key or step > latest_by_key[key]["step"]:
            latest_by_key[key] = {
                "step": step,
                "op": e["op"],
                "value": e.get("value"),
            }

    pred_by_id: dict[str, dict[str, str | None]] = {}
    retrieval_by_id: dict[str, dict[str, bool]] = {}
    for row in rows:
        key = row["meta"]["key"]
        chosen = latest_by_key[key]
        value = None if str(chosen["op"]).upper() == "CLEAR" else chosen.get("value")
        pred_by_id[row["id"]] = {"value": value}
        retrieval_by_id[row["id"]] = {
            "correct_included": True,
            "dropped_correct": False,
            "gold_missing": False,
        }

    counts = drift_mod.compute_drift_counts(
        data_rows=rows, pred_by_id=pred_by_id, retrieval_by_id=retrieval_by_id
    )
    metrics = counts.as_metrics()
    assert metrics["step_rate"] > 0
    assert metrics["persistence_rate"] > 0


def test_focus_drift_uses_sibling_value():
    cfg = _make_focus_cfg()
    ep = generate_episode(seed=5, episode_id="E0101", cfg=cfg)
    rows = ep["rows"]
    book = rows[0]["book"]
    entries = parse_book_ledger(book)
    assert entries

    last_set_by_key: dict[str, str] = {}
    sibling_hits = 0
    for e in entries:
        key = e["key"]
        if e["op"] == "SET":
            last_set_by_key[key] = str(e.get("value"))
        elif e["op"] == "NOTE":
            for other_key, other_val in last_set_by_key.items():
                if other_key != key and other_val == e.get("value"):
                    sibling_hits += 1
                    break
    assert sibling_hits > 0


def test_focus_drift_drift_accumulates():
    cfg = _make_focus_cfg()
    ep = generate_episode(seed=9, episode_id="E0102", cfg=cfg)
    rows = ep["rows"]
    book = rows[0]["book"]
    entries = parse_book_ledger(book)
    assert entries

    latest_by_key: dict[str, dict[str, str | None]] = {}
    for e in entries:
        key = e["key"]
        step = int(e["step"])
        if key not in latest_by_key or step > latest_by_key[key]["step"]:
            latest_by_key[key] = {
                "step": step,
                "op": e["op"],
                "value": e.get("value"),
            }

    pred_by_id: dict[str, dict[str, str | None]] = {}
    retrieval_by_id: dict[str, dict[str, bool]] = {}
    for row in rows:
        key = row["meta"]["key"]
        chosen = latest_by_key[key]
        value = None if str(chosen["op"]).upper() == "CLEAR" else chosen.get("value")
        pred_by_id[row["id"]] = {"value": value}
        retrieval_by_id[row["id"]] = {
            "correct_included": True,
            "dropped_correct": False,
            "gold_missing": False,
        }

    counts = drift_mod.compute_drift_counts(
        data_rows=rows, pred_by_id=pred_by_id, retrieval_by_id=retrieval_by_id
    )
    metrics = counts.as_metrics()
    assert metrics["step_rate"] > 0
    assert metrics["persistence_rate"] > 0
