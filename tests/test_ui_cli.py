import json
from types import SimpleNamespace
from pathlib import Path

from goldevidencebench import cli


def test_cmd_ui_score_writes_output(tmp_path: Path, monkeypatch) -> None:
    fixture_path = tmp_path / "fixture.jsonl"
    fixture_path.write_text(
        '{"id":"step_0001","candidates":[{"candidate_id":"btn_a","action_type":"click","label":"Next","role":"button","app_path":"Test","bbox":[0,0,10,10],"visible":true,"enabled":true,"modal_scope":null}],"gold":{"candidate_id":"btn_a"}}\n',
        encoding="utf-8",
    )
    out_path = tmp_path / "out.json"
    monkeypatch.setenv("GOLDEVIDENCEBENCH_UI_SELECTION_MODE", "gold")
    ns = SimpleNamespace(
        fixture=fixture_path,
        adapter="goldevidencebench.adapters.ui_fixture_adapter:create_adapter",
        observed=None,
        out=out_path,
    )
    rc = cli._cmd_ui_score(ns)
    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["metrics"]["selection_rate"] == 1.0
