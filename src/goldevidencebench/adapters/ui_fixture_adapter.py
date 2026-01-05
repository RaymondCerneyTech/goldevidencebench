from __future__ import annotations

import random
import zlib
from typing import Any

from ..util import get_env


class UIFixtureAdapter:
    def __init__(self) -> None:
        self.mode = get_env("UI_SELECTION_MODE", "first") or "first"
        seed_str = get_env("UI_SELECTION_SEED", "0") or "0"
        try:
            self.seed = int(seed_str)
        except ValueError:
            raise ValueError("UI_SELECTION_SEED must be an integer.") from None

        if self.mode not in {"gold", "first", "random", "abstain"}:
            raise ValueError(f"UI_SELECTION_MODE must be gold|first|random|abstain, got {self.mode}.")

    def _rng_for_row(self, row_id: str | None) -> random.Random:
        if row_id:
            row_hash = zlib.crc32(row_id.encode("utf-8")) & 0xFFFFFFFF
        else:
            row_hash = 0
        return random.Random(self.seed ^ row_hash)

    def predict(self, row: dict[str, Any], protocol: str = "closed_book") -> dict[str, Any]:
        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("UI row must include a candidates list.")

        candidate_ids = [
            candidate.get("candidate_id")
            for candidate in candidates
            if isinstance(candidate, dict) and isinstance(candidate.get("candidate_id"), str)
        ]
        gold = row.get("gold", {})
        gold_id = gold.get("candidate_id") if isinstance(gold, dict) else None

        selected: str | None
        if self.mode == "gold":
            selected = gold_id if isinstance(gold_id, str) else None
        elif self.mode == "first":
            selected = candidate_ids[0] if candidate_ids else None
        elif self.mode == "random":
            rng = self._rng_for_row(row.get("id") if isinstance(row.get("id"), str) else None)
            selected = rng.choice(candidate_ids) if candidate_ids else None
        elif self.mode == "abstain":
            selected = None
        else:
            selected = None

        return {"value": selected, "support_ids": []}


def create_adapter() -> UIFixtureAdapter:
    return UIFixtureAdapter()
