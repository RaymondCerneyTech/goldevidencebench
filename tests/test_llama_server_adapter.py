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


def test_predict_parse_failure_can_infer_latest_backticked_key(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "RIS-ANCHOR-0007-Q001",
        "question": "Do not be distracted. Return latest `part.alpha`.",
        "book": """# Episode

## State Ledger
- [U000031] step=1 SET part.alpha = v100
- [U000032] step=2 SET part.alpha = v200
""",
        "meta": {"query_type": "direct"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] == "v200"
    assert out["support_ids"] == ["U000032"]


def test_predict_parse_failure_can_infer_latest_authoritative_backticked_key(monkeypatch) -> None:
    monkeypatch.setattr(llama_server_adapter, "_request_text", lambda **_: "not-json")
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "RIS-HOLDOUT-0001-Q001",
        "question": "Return latest authoritative value for `resolved.part.beta`.",
        "book": """# Episode

## State Ledger
- [U000041] step=1 SET part.beta = v100
- [U000042] step=2 SET resolved.part.beta = v300
""",
        "meta": {"query_type": "direct"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] == "v300"
    assert out["support_ids"] == ["U000042"]


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


def test_predict_compression_loss_bounded_normalizes_null_to_empty_compact_state(monkeypatch) -> None:
    monkeypatch.setattr(
        llama_server_adapter,
        "_request_text",
        lambda **_: '{"value": null, "support_ids": []}',
    )
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "CLB-HOLDOUT-0014-Q001",
        "question": "Build compact state.",
        "book": """# Episode

## State Ledger
- [U000001] step=1 CLEAR tag.00
""",
        "meta": {
            "family": "compression_loss_bounded",
            "requires_citation": False,
        },
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] == {"compact_state": {}}
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
    assert isinstance(out["value"], dict)
    assert out["value"]["decision"] == "retrieve"
    assert out["value"]["answer"] is None
    assert out["value"]["confidence"] == 0.0
    assert out["value"]["needed_info"] == ["policy.region_override_cap"]
    assert out["support_ids"] == []


def test_predict_epistemic_parse_failure_attempts_single_repair(monkeypatch) -> None:
    calls: list[str] = []

    def fake_request_text(**kwargs):
        calls.append(str(kwargs.get("prompt") or ""))
        if len(calls) == 1:
            return "not-json"
        return (
            '{"decision":"retrieve","answer":null,"confidence":0.25,'
            '"needed_info":["policy.region_override_cap"],"support_ids":["U000201"]}'
        )

    monkeypatch.setattr(llama_server_adapter, "_request_text", fake_request_text)
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "EPI-HOLDOUT-0003-Q001",
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
    assert len(calls) == 2
    assert isinstance(out["value"], dict)
    assert out["value"]["decision"] == "retrieve"
    assert out["value"]["confidence"] == 0.25
    assert out["value"]["needed_info"] == ["policy.region_override_cap"]
    assert out["support_ids"] == ["U000201"]


def test_predict_strips_persona_directive_from_question(monkeypatch) -> None:
    captured_prompt = {"value": ""}

    def fake_request_text(**kwargs):
        captured_prompt["value"] = str(kwargs.get("prompt") or "")
        return '{"value":"amber-0001","support_ids":["U000031"]}'

    monkeypatch.setattr(llama_server_adapter, "_request_text", fake_request_text)
    adapter = LlamaServerAdapter(server_url="http://localhost:8080/completion")
    row = {
        "id": "Q004",
        "question": (
            "[PERSONA v1: creative writer]\n"
            "Answer with a creative narrative voice.\n\n"
            "[ORIGINAL QUESTION]\n"
            "Question Q004: What is the value of tag.03?"
        ),
        "book": """# Episode

## State Ledger
- [U000031] step=1 SET tag.03 = amber-0001
""",
        "meta": {"query_type": "direct"},
    }

    out = adapter.predict(row, protocol="closed_book")
    assert out["value"] == "amber-0001"
    assert out["support_ids"] == ["U000031"]
    assert "[PERSONA v1" not in captured_prompt["value"]
    assert "[ORIGINAL QUESTION]" not in captured_prompt["value"]


def test_request_payload_sets_deterministic_sampling_seed(monkeypatch) -> None:
    captured_payload: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"content":"{\\"value\\":null,\\"support_ids\\":[]}"}'

    def fake_urlopen(req, timeout=None):
        body = req.data.decode("utf-8")
        captured_payload.update(__import__("json").loads(body))
        return _FakeResponse()

    monkeypatch.setattr(llama_server_adapter.urllib.request, "urlopen", fake_urlopen)
    text = llama_server_adapter._request_text(
        url="http://localhost:8080/completion",
        prompt="Q",
        max_tokens=8,
        n_ctx=128,
        request_template=None,
        timeout_s=1.0,
    )
    assert text
    assert captured_payload["temperature"] == 0.0
    assert captured_payload["top_k"] == 1
    assert captured_payload["seed"] == 0
