from __future__ import annotations

from goldevidencebench.state_store import create_state_store


def test_state_store_stable_entity_ids() -> None:
    store = create_state_store("current")
    first_id = store.set("account.balance", "100")
    second_id = store.set("account.balance", "120")
    cleared_id = store.clear("account.balance")
    restored_id = store.set("account.balance", "140")

    assert first_id == second_id == cleared_id == restored_id
    assert store.get("account.balance") == "140"


def test_state_store_deterministic_replay() -> None:
    store = create_state_store("current")
    store.set("k1", "v1")
    store.set("k2", "v2")
    store.clear("k1")
    store.set("k3", "v3")
    events = store.events()
    snapshot_before = store.snapshot()

    replay_store = create_state_store("current")
    replay_store.replay(events)
    snapshot_after = replay_store.snapshot()

    assert snapshot_before["active"] == snapshot_after["active"]
    before_records = {(r["key"], r["entity_id"]) for r in snapshot_before["records"]}
    after_records = {(r["key"], r["entity_id"]) for r in snapshot_after["records"]}
    assert before_records == after_records


def test_state_store_reversible_updates() -> None:
    store = create_state_store("current")
    store.set("session.token", "abc")
    assert store.get("session.token") == "abc"
    store.clear("session.token")
    assert store.get("session.token") is None
    store.set("session.token", "xyz")
    assert store.get("session.token") == "xyz"
