from __future__ import annotations

from typing import Any


class MockAdapter:
    def __init__(self, *, mode: str = "oracle") -> None:
        self.mode = mode

    def predict(self, row: dict[str, Any], *, protocol: str = "open_book") -> dict[str, Any]:
        gold = row.get("gold", {})
        value = gold.get("value")
        supports = gold.get("support_ids") or gold.get("support_id") or []
        if isinstance(supports, str):
            supports = [supports]
        return {"value": value, "support_ids": supports}


def create_adapter() -> MockAdapter:
    return MockAdapter()
