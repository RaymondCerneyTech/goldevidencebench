from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _extract_fact(row: dict) -> str | None:
    fact = row.get("fact")
    if isinstance(fact, str) and fact:
        return fact
    text = row.get("text") or ""
    match = re.search(r"FACT:\s*(.+)", text)
    if match:
        return match.group(1).strip()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build open-book dataset from a doc index JSONL.")
    parser.add_argument("--index", required=True, help="Doc index JSONL path.")
    parser.add_argument("--out", required=True, help="Output dataset JSONL path.")
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        raise SystemExit(f"Doc index not found: {index_path}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    doc_ids: list[str] = []
    parsed_rows: list[dict[str, str]] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        doc_id = row.get("id") or row.get("doc_id")
        if not doc_id:
            continue
        fact = _extract_fact(row)
        if not fact:
            continue
        doc_ids.append(str(doc_id))
        parsed_rows.append({"doc_id": str(doc_id), "fact": fact})

    for item in parsed_rows:
        doc_id = item["doc_id"]
        fact = item["fact"]
        qid = f"{doc_id}-Q001"
        question = (
            f"In document {doc_id}, what is the FACT line?\n"
            "Return JSON with keys: value, support_ids."
        )
        rows.append(
            {
                "id": qid,
                "episode_id": doc_id,
                "schema_version": "1.0",
                "document": "",
                "book": "",
                "question": question,
                "gold": {"value": fact, "support_id": doc_id, "support_ids": [doc_id]},
                "meta": {
                    "requires_citation": True,
                    "citation_mode": "doc_id",
                    "doc_ids": doc_ids,
                    "query_type": "open_book",
                    "state_mode": "doc",
                },
            }
        )

    if not rows:
        raise SystemExit("No dataset rows created. Check doc index contents.")

    out_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
