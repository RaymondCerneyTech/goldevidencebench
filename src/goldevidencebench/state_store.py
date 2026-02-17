from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from goldevidencebench.util import get_env


BACKEND_CURRENT = "current"
BACKEND_SPARSE_SET = "sparse_set"
DEFAULT_BACKEND = BACKEND_CURRENT


@dataclass
class StateRecord:
    entity_id: str
    key: str
    value: Any
    active: bool
    created_seq: int
    updated_seq: int


class StateStore(ABC):
    @property
    @abstractmethod
    def backend(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def experimental(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get(self, key: str) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    def clear(self, key: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def apply_patch(self, patch: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> list[StateRecord]:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def replay(self, events: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    @abstractmethod
    def events(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class CurrentStateStore(StateStore):
    def __init__(self) -> None:
        self._next_id = 1
        self._seq = 0
        self._key_to_id: dict[str, str] = {}
        self._records: dict[str, StateRecord] = {}
        self._events: list[dict[str, Any]] = []

    @property
    def backend(self) -> str:
        return BACKEND_CURRENT

    @property
    def experimental(self) -> bool:
        return False

    def _new_id(self) -> str:
        entity_id = f"S{self._next_id:06d}"
        self._next_id += 1
        return entity_id

    def _ensure_record(self, key: str) -> StateRecord:
        if key in self._key_to_id:
            return self._records[self._key_to_id[key]]
        entity_id = self._new_id()
        self._seq += 1
        record = StateRecord(
            entity_id=entity_id,
            key=key,
            value=None,
            active=False,
            created_seq=self._seq,
            updated_seq=self._seq,
        )
        self._key_to_id[key] = entity_id
        self._records[entity_id] = record
        return record

    def get(self, key: str) -> Any | None:
        record = self._ensure_record(key)
        return record.value if record.active else None

    def set(self, key: str, value: Any) -> str:
        record = self._ensure_record(key)
        self._seq += 1
        record.value = value
        record.active = True
        record.updated_seq = self._seq
        event = {"op": "set", "key": key, "value": value, "entity_id": record.entity_id, "seq": self._seq}
        self._events.append(event)
        return record.entity_id

    def clear(self, key: str) -> str:
        record = self._ensure_record(key)
        self._seq += 1
        record.value = None
        record.active = False
        record.updated_seq = self._seq
        event = {"op": "clear", "key": key, "entity_id": record.entity_id, "seq": self._seq}
        self._events.append(event)
        return record.entity_id

    def apply_patch(self, patch: dict[str, Any]) -> list[str]:
        entity_ids: list[str] = []
        set_ops = patch.get("set")
        if isinstance(set_ops, dict):
            for key, value in set_ops.items():
                if isinstance(key, str):
                    entity_ids.append(self.set(key, value))
        clear_ops = patch.get("clear")
        if isinstance(clear_ops, list):
            for key in clear_ops:
                if isinstance(key, str):
                    entity_ids.append(self.clear(key))
        return entity_ids

    def list_active(self) -> list[StateRecord]:
        active = [record for record in self._records.values() if record.active]
        active.sort(key=lambda record: record.created_seq)
        return active

    def snapshot(self) -> dict[str, Any]:
        active = self.list_active()
        return {
            "backend": self.backend,
            "experimental": self.experimental,
            "next_id": self._next_id,
            "active": {record.key: record.value for record in active},
            "records": [
                {
                    "entity_id": record.entity_id,
                    "key": record.key,
                    "value": record.value,
                    "active": record.active,
                    "created_seq": record.created_seq,
                    "updated_seq": record.updated_seq,
                }
                for record in sorted(self._records.values(), key=lambda item: item.created_seq)
            ],
            "events": list(self._events),
        }

    def replay(self, events: list[dict[str, Any]]) -> None:
        self._next_id = 1
        self._seq = 0
        self._key_to_id = {}
        self._records = {}
        self._events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            op = event.get("op")
            key = event.get("key")
            if not isinstance(key, str):
                continue
            if op == "set":
                self.set(key, event.get("value"))
            elif op == "clear":
                self.clear(key)

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)


class SparseSetStateStore(CurrentStateStore):
    @property
    def backend(self) -> str:
        return BACKEND_SPARSE_SET

    @property
    def experimental(self) -> bool:
        return True


def _normalize_backend_name(raw: str | None) -> str:
    if not raw:
        return DEFAULT_BACKEND
    value = raw.strip().lower()
    if value in {BACKEND_CURRENT, BACKEND_SPARSE_SET}:
        return value
    return DEFAULT_BACKEND


def resolve_backend(backend: str | None = None) -> str:
    if backend:
        return _normalize_backend_name(backend)
    return _normalize_backend_name(get_env("STATE_STORE_BACKEND", DEFAULT_BACKEND))


def create_state_store(backend: str | None = None) -> StateStore:
    resolved = resolve_backend(backend)
    if resolved == BACKEND_SPARSE_SET:
        return SparseSetStateStore()
    return CurrentStateStore()
