from __future__ import annotations

import argparse
import json
from pathlib import Path


def uid(n: int) -> str:
    return f"U{n:06X}"


ENTRIES = [
    {
        "id": "POL001-Q001",
        "episode": "POL001",
        "key": "tag.00",
        "label": "Data retention days",
        "policy": "Customer data retention window.",
        "current": "retention_days=45",
        "old": "retention_days=30",
        "decoy": "retention_days=90",
        "bucket": "stale_doc",
    },
    {
        "id": "POL002-Q001",
        "episode": "POL002",
        "key": "tag.01",
        "label": "Password rotation",
        "policy": "Password rotation cadence.",
        "current": "password_rotation_days=90",
        "old": "password_rotation_days=60",
        "decoy": "password_rotation_days=120",
        "bucket": "stale_doc",
    },
    {
        "id": "POL003-Q001",
        "episode": "POL003",
        "key": "tag.02",
        "label": "Incident response",
        "policy": "Initial incident response time.",
        "current": "incident_response_hours=4",
        "old": "incident_response_hours=24",
        "decoy": "incident_response_hours=8",
        "bucket": "stale_doc",
    },
    {
        "id": "POL004-Q001",
        "episode": "POL004",
        "key": "tag.03",
        "label": "Access approval",
        "policy": "Role required to approve access.",
        "current": "access_approval_role=security_lead",
        "old": "access_approval_role=it_manager",
        "decoy": "access_approval_role=team_lead",
        "bucket": "stale_doc",
    },
    {
        "id": "POL005-Q001",
        "episode": "POL005",
        "key": "tag.04",
        "label": "Data export SLA",
        "policy": "Time limit to deliver customer exports.",
        "current": "data_export_sla_days=7",
        "old": "data_export_sla_days=14",
        "decoy": "data_export_sla_days=30",
        "bucket": "stale_doc",
    },
    {
        "id": "POL006-Q001",
        "episode": "POL006",
        "key": "tag.05",
        "label": "Deletion completion",
        "policy": "Time to complete deletion requests.",
        "current": "deletion_request_days=30",
        "old": "deletion_request_days=60",
        "decoy": "deletion_request_days=90",
        "bucket": "stale_doc",
    },
    {
        "id": "POL007-Q001",
        "episode": "POL007",
        "key": "tag.06",
        "label": "Log retention",
        "policy": "Operational log retention duration.",
        "current": "log_retention_days=180",
        "old": None,
        "decoy": "log_retention_days=365",
        "bucket": "authority_decoy",
    },
    {
        "id": "POL008-Q001",
        "episode": "POL008",
        "key": "tag.07",
        "label": "Encryption standard",
        "policy": "Required encryption standard for storage.",
        "current": "encryption_standard=AES-256",
        "old": None,
        "decoy": "encryption_standard=AES-128",
        "bucket": "authority_decoy",
    },
    {
        "id": "POL009-Q001",
        "episode": "POL009",
        "key": "tag.08",
        "label": "PII sharing",
        "policy": "Whether PII sharing is allowed.",
        "current": "pii_sharing=prohibited",
        "old": None,
        "decoy": "pii_sharing=allowed_with_notice",
        "bucket": "authority_decoy",
    },
    {
        "id": "POL010-Q001",
        "episode": "POL010",
        "key": "tag.09",
        "label": "Backup frequency",
        "policy": "Backup cadence for production systems.",
        "current": "backup_frequency_hours=6",
        "old": None,
        "decoy": "backup_frequency_hours=24",
        "bucket": "authority_decoy",
    },
    {
        "id": "POL011-Q001",
        "episode": "POL011",
        "key": "tag.10",
        "label": "Vendor risk review",
        "policy": "Vendor risk review cadence.",
        "current": "vendor_review_months=12",
        "old": None,
        "decoy": "vendor_review_months=24",
        "bucket": "authority_decoy",
    },
    {
        "id": "POL012-Q001",
        "episode": "POL012",
        "key": "tag.11",
        "label": "MFA requirement",
        "policy": "Whether MFA is required for admin access.",
        "current": "mfa_required=yes",
        "old": None,
        "decoy": "mfa_required=no",
        "bucket": "authority_decoy",
    },
]


def build_episode(entry: dict[str, str], uid_start: int) -> tuple[str, str, str, int]:
    updates: list[tuple[str, int, str, str, str]] = []
    step = 1
    uid_counter = uid_start

    def add_update(op: str, value: str) -> str:
        nonlocal step, uid_counter
        u = uid(uid_counter)
        uid_counter += 1
        updates.append((op, step, u, entry["key"], value))
        step += 1
        return u

    support_uid = None
    if entry.get("old"):
        add_update("SET", entry["old"])
        add_update("NOTE", entry["decoy"])
        support_uid = add_update("SET", entry["current"])
        add_update("NOTE", entry["old"])
    else:
        support_uid = add_update("SET", entry["current"])
        add_update("NOTE", entry["decoy"])

    doc_lines = [
        f"# Policy Handbook Episode {entry['episode']}",
        "",
        "## Episode Log",
    ]
    for op, step_num, u, key, value in updates:
        doc_lines.append(f"- [{u}] UPDATE step={step_num} {op} {key} = {value}")
    doc_lines.extend(
        [
            "",
            "## Policy Notes",
            f"- Policy: {entry['policy']}",
        ]
    )
    if entry.get("old"):
        doc_lines.append(f"- Legacy policy: {entry['old']} (superseded).")
    doc_lines.append(f"- NOTE: {entry['decoy']} appears in older drafts.")
    document = "\n".join(doc_lines)

    book_lines = [
        f"# Policy Handbook Episode {entry['episode']}",
        "",
        "## Reading Rules",
        "- The STATE LEDGER is authoritative for current policy.",
        "- Only SET/CLEAR lines update state; NOTE lines are commentary.",
        "- Ignore NOTE/INFO lines when deciding the official policy.",
        "",
        "## Glossary (Tags)",
        f"- {entry['key']}: {entry['label']}",
        "",
        "## Chapter 1",
        f"Policy: {entry['policy']}",
    ]
    if entry.get("old"):
        book_lines.append(f"Legacy policy: {entry['old']} (superseded).")
    book_lines.append(f"Decoy text: {entry['decoy']} (non-authoritative).")
    book_lines.extend(["", "## State Ledger"])
    for op, step_num, u, key, value in updates:
        book_lines.append(f"- [{u}] step={step_num} {op} {key} = {value}")
    book = "\n".join(book_lines)

    return document, book, support_uid, uid_counter


def build_rows(entries: list[dict[str, str]]) -> list[dict]:
    rows = []
    uid_counter = 1
    for entry in entries:
        document, book, support_uid, uid_counter = build_episode(entry, uid_counter)
        question = (
            f"Question {entry['id']}: What is the current policy value for {entry['label']}?\n"
            "Return JSON with keys: value, support_ids."
        )
        rows.append(
            {
                "id": entry["id"],
                "episode_id": entry["episode"],
                "schema_version": "1.0",
                "document": document,
                "book": book,
                "question": question,
                "gold": {
                    "value": entry["current"],
                    "support_id": support_uid,
                    "support_ids": [support_uid],
                },
                "meta": {
                    "requires_citation": True,
                    "key": entry["key"],
                    "query_type": "direct",
                    "state_mode": "kv",
                    "has_instruction": False,
                },
            }
        )
    return rows


def _load_entries(path: Path) -> list[dict[str, str]]:
    raw = path.read_text(encoding="utf-8-sig")
    entries: list[dict[str, str]] = []
    if path.suffix.lower() == ".json":
        payload = json.loads(raw)
        if isinstance(payload, list):
            entries = [e for e in payload if isinstance(e, dict)]
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                entries.append(obj)
    if not entries:
        raise ValueError("No entries found in input file.")
    normalized: list[dict[str, str]] = []
    for idx, entry in enumerate(entries):
        entry = {str(k): v for k, v in entry.items()}
        label = entry.get("label") or entry.get("id") or f"Policy {idx+1}"
        entry_id = entry.get("id") or f"DOM{idx+1:03d}-Q001"
        episode = entry.get("episode") or f"DOM{idx+1:03d}"
        key = entry.get("key") or f"tag.{idx:02d}"
        policy = entry.get("policy") or label
        current = entry.get("current")
        decoy = entry.get("decoy")
        bucket = entry.get("bucket") or "stale_doc"
        if not current or not decoy:
            raise ValueError(f"Entry {entry_id} missing required fields: current/decoy.")
        normalized.append(
            {
                "id": entry_id,
                "episode": episode,
                "key": key,
                "label": label,
                "policy": policy,
                "current": current,
                "old": entry.get("old"),
                "decoy": decoy,
                "bucket": bucket,
            }
        )
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAG domain pack fixtures.")
    parser.add_argument(
        "--in",
        dest="input_path",
        help="Optional JSON/JSONL file with domain entries.",
    )
    parser.add_argument(
        "--out-dir",
        default="data",
        help="Output directory for domain packs.",
    )
    args = parser.parse_args()

    entries = ENTRIES
    if args.input_path:
        entries = _load_entries(Path(args.input_path))

    rows = build_rows(entries)
    stale = [row for row, entry in zip(rows, entries) if entry["bucket"] == "stale_doc"]
    authority = [row for row, entry in zip(rows, entries) if entry["bucket"] == "authority_decoy"]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    (out_dir / "rag_domain_stale.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in stale) + "\n",
        encoding="utf-8",
    )
    (out_dir / "rag_domain_authority.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in authority) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
