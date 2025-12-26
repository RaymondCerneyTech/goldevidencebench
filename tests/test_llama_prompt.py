from __future__ import annotations

from goldevidencebench.adapters.llama_prompt import build_prompt, extract_ledger, truncate_tokens


def test_extract_ledger_returns_ledger_section() -> None:
    book = "Header\n\n## State Ledger\n- [U0001] step=1 SET tag.00 = red\n"
    ledger = extract_ledger(book)
    assert ledger.startswith("## State Ledger")
    assert "Header" not in ledger


def test_extract_ledger_falls_back_when_missing() -> None:
    book = "No ledger here."
    assert extract_ledger(book) == book


def test_truncate_tokens_keeps_tail() -> None:
    text = "a b c d e"
    assert truncate_tokens(text, 3) == "c d e"


def test_truncate_tokens_uses_tokenizer_when_provided() -> None:
    text = "hello"

    def fake_tokenize(data: bytes) -> list[int]:
        return list(data)

    def fake_detokenize(tokens: list[int]) -> bytes:
        return bytes(tokens)

    assert (
        truncate_tokens(text, 3, tokenize=fake_tokenize, detokenize=fake_detokenize)
        == "llo"
    )


def test_build_prompt_includes_ledger_and_question() -> None:
    ledger = "## State Ledger\n- [U1] step=1 SET tag.00 = red"
    question = "What is tag.00?"
    prompt = build_prompt(ledger=ledger, question=question)
    assert ledger in prompt
    assert question in prompt
