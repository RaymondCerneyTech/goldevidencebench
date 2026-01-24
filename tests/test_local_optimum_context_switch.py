import json
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_context_switch_fixture_uses_context_guard() -> None:
    rows = _load_jsonl(
        Path("data/ui_minipilot_local_optimum_context_switch_fixture.jsonl")
    )
    guarded = [row for row in rows if isinstance(row.get("requires_state"), dict)]
    assert len(guarded) == 2
    for row in guarded:
        context = row["requires_state"].get("context")
        assert context in {"primary", "secondary"}
        gold_id = row["gold"]["candidate_id"]
        assert context in gold_id


def test_context_switch_ambiguous_has_duplicate_buttons() -> None:
    rows = _load_jsonl(
        Path("data/ui_minipilot_local_optimum_context_switch_ambiguous_fixture.jsonl")
    )
    assert rows
    for row in rows:
        assert row.get("abstain_expected") is True
        labels = [candidate.get("label") for candidate in row["candidates"]]
        assert len(set(labels)) == 1
        bboxes = [candidate.get("bbox") for candidate in row["candidates"]]
        assert len(set(tuple(bbox) for bbox in bboxes)) == 1
