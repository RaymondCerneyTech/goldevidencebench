from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from goldevidencebench import walls as walls_mod


def _norm_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return str(value).strip() or None


def _gold_present(diag: dict[str, Any]) -> bool:
    if diag.get("gold_missing") is True:
        return False
    if diag.get("correct_included") is not True:
        return False
    if diag.get("dropped_correct") is True:
        return False
    return True


@dataclass
class DriftCounts:
    steps_total: int = 0
    steps_drift: int = 0
    steps_persist: int = 0
    wrong_commit: int = 0
    episodes_total: int = 0
    episodes_drift: int = 0

    def add(self, other: DriftCounts) -> None:
        self.steps_total += other.steps_total
        self.steps_drift += other.steps_drift
        self.steps_persist += other.steps_persist
        self.wrong_commit += other.wrong_commit
        self.episodes_total += other.episodes_total
        self.episodes_drift += other.episodes_drift

    def as_metrics(self) -> dict[str, Any]:
        step_rate = (self.steps_drift / self.steps_total) if self.steps_total else None
        persistence_rate = (self.steps_persist / self.steps_total) if self.steps_total else None
        wrong_commit_rate = (self.wrong_commit / self.steps_total) if self.steps_total else None
        run_rate = (self.episodes_drift / self.episodes_total) if self.episodes_total else None
        return {
            "step_rate": step_rate,
            "persistence_rate": persistence_rate,
            "wrong_commit_rate": wrong_commit_rate,
            "run_rate": run_rate,
            "step_count": self.steps_total,
            "run_count": self.episodes_total,
        }


def compute_drift_counts(
    *,
    data_rows: list[dict[str, Any]],
    pred_by_id: dict[str, dict[str, Any]],
    retrieval_by_id: dict[str, dict[str, Any]],
) -> DriftCounts:
    episodes: dict[str, list[dict[str, Any]]] = {}
    for row in data_rows:
        episode_id = str(row.get("episode_id") or "episode")
        episodes.setdefault(episode_id, []).append(row)

    counts = DriftCounts()
    for _episode_id, rows in episodes.items():
        rows_sorted = sorted(
            rows, key=lambda r: int(r.get("meta", {}).get("q_index") or 0)
        )
        belief: dict[str, str | None] = {}
        episode_steps = 0
        episode_drifted = False
        for row in rows_sorted:
            rid = row.get("id")
            if not rid:
                continue
            diag = retrieval_by_id.get(rid)
            if not diag or not _gold_present(diag):
                continue
            key = row.get("meta", {}).get("key") or row.get("key")
            if not key:
                continue
            gold_value = _norm_value(row.get("gold", {}).get("value"))
            if gold_value is None:
                continue
            pred = pred_by_id.get(rid, {})
            pred_value = _norm_value(pred.get("value"))

            episode_steps += 1
            prev_value = belief.get(key)
            if prev_value is not None and prev_value != gold_value:
                counts.steps_drift += 1
                episode_drifted = True
                if pred_value is None or pred_value != gold_value:
                    counts.steps_persist += 1

            if pred_value is not None and pred_value != gold_value:
                counts.wrong_commit += 1

            if pred_value is not None:
                belief[key] = pred_value

        if episode_steps:
            counts.steps_total += episode_steps
            counts.episodes_total += 1
            if episode_drifted:
                counts.episodes_drift += 1

    return counts


def find_drift_wall(
    points: list[walls_mod.WallPoint],
    *,
    threshold: float,
    direction: str,
) -> tuple[walls_mod.WallPoint | None, walls_mod.WallPoint | None]:
    ordered = sorted(points, key=lambda p: p.param)
    return walls_mod.find_wall(ordered, threshold=threshold, direction=direction)


def wall_payload(
    *,
    points: list[walls_mod.WallPoint],
    metric_path: str,
    param_key: str,
    threshold: float,
    direction: str,
    state_mode: str | None,
    distractor_profile: str | None,
    last_ok: walls_mod.WallPoint | None,
    wall: walls_mod.WallPoint | None,
) -> dict[str, Any]:
    def _entry(point: walls_mod.WallPoint | None) -> dict[str, Any] | None:
        if not point:
            return None
        return {
            "param": point.param,
            "metric": point.metric,
            "run_dir": str(point.run_dir),
        }

    return {
        "metric_path": metric_path,
        "param_key": param_key,
        "threshold": threshold,
        "direction": direction,
        "state_mode": state_mode,
        "distractor_profile": distractor_profile,
        "points": [
            {"param": p.param, "metric": p.metric, "run_dir": str(p.run_dir)}
            for p in points
        ],
        "last_ok": _entry(last_ok),
        "wall": _entry(wall),
    }
