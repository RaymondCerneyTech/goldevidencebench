from __future__ import annotations

import goldevidencebench.adapters.llama_server_adapter as llama_server_adapter
from goldevidencebench.adapters.llama_server_adapter import (
    LlamaServerAdapter,
    _canonical_value_for_selected,
)


def test_canonical_value_for_selected_direct_query_uses_ledger_value() -> None:
    row = {
        "id": "DOM003-Q001",
        "meta": {
            "key": "tag.03",
            "query_type": "direct",
            "state_mode": "kv",
        },
    }
    book = """# Episode

## State Ledger
- [U000005] step=1 SET tag.02 = retention_days=45
- [U000006] step=2 SET tag.03 = retention_days_eu=30
- [U000007] step=3 NOTE tag.03 = retention_days_eu=60
"""
    out = _canonical_value_for_selected(
        row=row,
        book=book,
        selected_uid="U000006",
        predicted_value="30",
    )
    assert out == "retention_days_eu=30"


def test_canonical_value_for_selected_derived_query_keeps_predicted_value() -> None:
    row = {
        "id": "Q001",
        "meta": {
            "key": "tag.00",
            "query_type": "derived",
            "derived_op": "color",
            "state_mode": "kv",
        },
    }
    book = """# Episode

## State Ledger
- [U0A1B2C] step=12 SET tag.00 = amber-0001
"""
    out = _canonical_value_for_selected(
        row=row,
        book=book,
        selected_uid="U0A1B2C",
        predicted_value="amber",
    )
    assert out == "amber"


def test_predict_parse_failure_backfills_support_id_for_direct_clear(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "Q001",
        "question": "What is the value of tag.02?",
        "book": """# Episode

## State Ledger
- [U000001] step=1 SET tag.02 = retention_days=45
- [U000002] step=2 CLEAR tag.02
""",
        "meta": {"key": "tag.02", "query_type": "direct"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] is None
    assert out["support_ids"] == ["U000002"]


def test_predict_parse_failure_backfills_support_id_for_derived_clear(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "Q002",
        "question": "What is the color prefix of tag.05?",
        "book": """# Episode

## State Ledger
- [U000011] step=1 SET tag.05 = amber-0001
- [U000012] step=2 CLEAR tag.05
""",
        "meta": {"key": "tag.05", "query_type": "derived", "derived_op": "color"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] is None
    assert out["support_ids"] == ["U000012"]


def test_predict_parse_failure_unknown_key_does_not_invent_support_ids(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "Q003",
        "question": "What is the value of tag.99?",
        "book": """# Episode

## State Ledger
- [U000021] step=1 SET tag.01 = amber-0001
""",
        "meta": {"key": "tag.99", "query_type": "direct"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] is None
    assert out["support_ids"] == []


def test_predict_parse_failure_direct_set_backfills_canonical_value(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "Q003B",
        "question": "What is the value of tag.03?",
        "book": """# Episode

## State Ledger
- [U000021] step=1 SET tag.03 = retention_days_eu=30
""",
        "meta": {"key": "tag.03", "query_type": "direct"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] == "retention_days_eu=30"
    assert out["support_ids"] == ["U000021"]


def test_predict_parse_failure_can_infer_key_from_question(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "Q004",
        "question": "Question Q004: What is the value of tag.03?",
        "book": """# Episode

## State Ledger
- [U000031] step=1 SET tag.03 = amber-0001
""",
        "meta": {"query_type": "direct"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] == "amber-0001"
    assert out["support_ids"] == ["U000031"]


def test_predict_respects_row_requires_citation_false(monkeypatch) -> None:
    monkeypatch.setattr(
        llama_server_adapter,
        "_request_text",
        lambda **_: "{\"value\":\"ok\",\"support_ids\":[\"U000001\"]}",
    )
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "Q005",
        "question": "Return JSON.",
        "book": """# Episode

## State Ledger
- [U000001] step=1 SET tag.00 = amber-0001
""",
        "meta": {
            "key": "tag.00",
            "query_type": "direct",
            "requires_citation": False,
        },
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] == "ok"
    assert out["support_ids"] == []


def test_predict_compression_family_accepts_object_value(monkeypatch) -> None:
    monkeypatch.setattr(
        llama_server_adapter,
        "_request_text",
        lambda **_: "{\"value\":{\"compact_state\":{\"tag.00\":\"amber-0001\"}},\"support_ids\":[]}",
    )
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "CLB-ANCHOR-0001-Q001",
        "question": "Build compact state.",
        "book": """# Episode

## State Ledger
- [U000001] step=1 SET tag.00 = amber-0001
""",
        "meta": {
            "family": "compression_loss_bounded",
            "requires_citation": False,
        },
    }

    out = adapter.predict(row, protocol="closed_book")
    assert isinstance(out.get("value"), dict)
    assert out["value"] == {"compact_state": {"tag.00": "amber-0001"}}
    assert out["support_ids"] == []


def test_predict_compression_family_accepts_top_level_compact_state(monkeypatch) -> None:
    monkeypatch.setattr(
        llama_server_adapter,
        "_request_text",
        lambda **_: "{\"compact_state\":{\"tag.00\":\"amber-0001\"}}",
    )
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "CLB-ANCHOR-0001-Q001",
        "question": "Build compact state.",
        "book": """# Episode

## State Ledger
- [U000001] step=1 SET tag.00 = amber-0001
""",
        "meta": {
            "family": "compression_loss_bounded",
            "requires_citation": False,
        },
    }

    out = adapter.predict(row, protocol="closed_book")
    assert isinstance(out.get("value"), dict)
    assert out["value"] == {"compact_state": {"tag.00": "amber-0001"}}
    assert out["support_ids"] == []


def test_predict_epistemic_family_preserves_structured_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        llama_server_adapter,
        "_request_text",
        lambda **_: (
            '{"decision":"retrieve","answer":null,"confidence":0.33,'
            '"needed_info":["policy.region_override_cap"],"support_ids":["U000111"]}'
        ),
    )
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "EPI-HOLDOUT-0001-Q001",
        "question": "If evidence is missing, do not guess.",
        "book": """# Episode

## State Ledger
- [U000111] step=1 SET policy.retention_days = 30
""",
        "meta": {
            "family": "epistemic_calibration_suite",
            "family_id": "unknown_unanswerable",
            "key": "policy.region_override_cap",
            "query_type": "direct",
        },
    }

    out = adapter.predict(row, protocol="closed_book")
    assert isinstance(out.get("value"), dict)
    assert out["value"]["decision"] == "retrieve"
    assert out["value"]["confidence"] == 0.33
    assert out["value"]["needed_info"] == ["policy.region_override_cap"]
    assert out["support_ids"] == ["U000111"]


def test_predict_epistemic_parse_failure_does_not_backfill_value(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "EPI-HOLDOUT-0002-Q001",
        "question": "Unknown key; do not guess.",
        "book": """# Episode

## State Ledger
- [U000201] step=1 SET policy.retention_days = 30
""",
        "meta": {
            "family": "epistemic_calibration_suite",
            "family_id": "unknown_unanswerable",
            "key": "policy.region_override_cap",
            "query_type": "direct",
        },
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] is None
    assert out["support_ids"] == []
