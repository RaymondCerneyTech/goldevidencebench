from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _require_pypdf() -> None:
    try:
        import pypdf  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: pypdf. Install with: python -m pip install -e \".[pdf]\""
        ) from exc


def _extract_lines(pdf_path: Path) -> list[str]:
    _require_pypdf()
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(pdf_path))
    lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.isdigit():
                continue
            lines.append(line)
    return lines


def _filter_lines(lines: list[str], min_len: int, max_len: int) -> list[str]:
    seen: set[str] = set()
    filtered: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        if len(line) < min_len or len(line) > max_len:
            continue
        if not any(ch.isalpha() for ch in line):
            continue
        filtered.append(line)
    return filtered


def _fact_label(line: str, max_words: int = 8) -> str:
    tokens = re.sub(r"[^0-9a-zA-Z]+", " ", line).split()
    return " ".join(tokens[:max_words])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a JSONL doc index from a PDF.")
    parser.add_argument("--pdf-path", required=True, help="Path to the source PDF.")
    parser.add_argument("--out", required=True, help="Output JSONL path.")
    parser.add_argument("--max-docs", type=int, default=24, help="Maximum docs to emit.")
    parser.add_argument("--min-line-len", type=int, default=30, help="Minimum line length.")
    parser.add_argument("--max-line-len", type=int, default=160, help="Maximum line length.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    lines = _extract_lines(pdf_path)
    candidates = _filter_lines(lines, args.min_line_len, args.max_line_len)
    if not candidates:
        raise SystemExit("No suitable lines extracted from PDF.")

    selected = candidates[: args.max_docs]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx, line in enumerate(selected, start=1):
        doc_id = f"DOC{idx:03d}"
        fact = line
        label = _fact_label(line)
        title = f"{doc_id} - {label}".strip()
        text = f"[{doc_id}] FACT: {fact}"
        rows.append({"id": doc_id, "title": title, "text": text, "fact": fact})

    out_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
