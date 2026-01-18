from __future__ import annotations

from goldevidencebench.memory import verify_memory_entries


def test_verify_memory_repo_citation_ok(tmp_path) -> None:
    doc = tmp_path / "demo.txt"
    doc.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    entry = {
        "id": "mem_ok",
        "claim_text": "beta",
        "citations": [
            {
                "type": "repo",
                "file_path": "demo.txt",
                "line_start": 2,
                "line_end": 2,
                "snippet": "beta",
            }
        ],
        "confidence": 0.6,
        "used": True,
    }
    results, summary = verify_memory_entries([entry], root=tmp_path)
    assert results[0]["ok"] is True
    assert summary["memory_verified_rate"] == 1.0
    assert summary["memory_invalid_rate"] == 0.0


def test_verify_memory_repo_citation_mismatch(tmp_path) -> None:
    doc = tmp_path / "demo.txt"
    doc.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    entry = {
        "id": "mem_bad",
        "claim_text": "beta",
        "citations": [
            {
                "type": "repo",
                "file_path": "demo.txt",
                "line_start": 2,
                "line_end": 2,
                "snippet": "betta",
            }
        ],
        "confidence": 0.95,
        "used": True,
    }
    results, summary = verify_memory_entries([entry], root=tmp_path)
    assert results[0]["ok"] is False
    assert "stale_memory" in results[0]["tags"]
    assert "overconfident_memory" in results[0]["tags"]
    assert summary["memory_invalid_rate"] == 1.0
