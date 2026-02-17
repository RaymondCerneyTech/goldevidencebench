from __future__ import annotations

from goldevidencebench.state_store import (
    BACKEND_CURRENT,
    BACKEND_SPARSE_SET,
    create_state_store,
    resolve_backend,
)


def test_state_store_backend_selection_default_current(monkeypatch) -> None:
    monkeypatch.delenv("GOLDEVIDENCEBENCH_STATE_STORE_BACKEND", raising=False)
    assert resolve_backend() == BACKEND_CURRENT
    store = create_state_store()
    assert store.backend == BACKEND_CURRENT
    assert store.experimental is False


def test_state_store_backend_selection_sparse_set_experimental(monkeypatch) -> None:
    monkeypatch.setenv("GOLDEVIDENCEBENCH_STATE_STORE_BACKEND", BACKEND_SPARSE_SET)
    assert resolve_backend() == BACKEND_SPARSE_SET
    store = create_state_store()
    assert store.backend == BACKEND_SPARSE_SET
    assert store.experimental is True
