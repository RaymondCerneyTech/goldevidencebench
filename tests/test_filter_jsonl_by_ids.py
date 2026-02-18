from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def test_filter_jsonl_by_ids_includes_only_requested_ids(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "filter_jsonl_by_ids.py"
    data_path = tmp_path / "data.jsonl"
    ids_path = tmp_path / "ids.txt"
    out_path = tmp_path / "filtered.jsonl"

    _write_jsonl(
        data_path,
        [
            {"id": "A", "x": 1},
            {"id": "B", "x": 2},
            {"id": "C", "x": 3},
        ],
    )
    ids_path.write_text("B\nC\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script), "--data", str(data_path), "--ids", str(ids_path), "--out", str(out_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["id"] for row in rows] == ["B", "C"]


def test_filter_jsonl_by_ids_invert_excludes_requested_ids(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "filter_jsonl_by_ids.py"
    data_path = tmp_path / "data.jsonl"
    ids_path = tmp_path / "ids.txt"
    out_path = tmp_path / "filtered_invert.jsonl"

    _write_jsonl(
        data_path,
        [
            {"id": "A", "x": 1},
            {"id": "B", "x": 2},
            {"id": "C", "x": 3},
        ],
    )
    ids_path.write_text("B\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--ids",
            str(ids_path),
            "--out",
            str(out_path),
            "--invert",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["id"] for row in rows] == ["A", "C"]
