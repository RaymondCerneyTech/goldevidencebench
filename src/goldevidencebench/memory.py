from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .util import read_jsonl


def _normalize(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def _extract_lines(path: Path, line_start: int, line_end: int) -> str | None:
    if line_start < 1 or line_end < line_start:
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if line_start > len(lines):
        return None
    safe_end = min(line_end, len(lines))
    return "\n".join(lines[line_start - 1 : safe_end])


def _verify_repo_citation(
    citation: dict[str, Any], *, root: Path, claim_text: str
) -> tuple[bool, list[str], list[str]]:
    reasons: list[str] = []
    tags: list[str] = []
    file_path = citation.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        reasons.append("missing_file_path")
        tags.append("invalid_citation")
        return False, reasons, tags
    path = root / file_path
    if not path.exists():
        reasons.append(f"missing_file:{file_path}")
        tags.append("invalid_citation")
        return False, reasons, tags
    try:
        line_start = int(citation.get("line_start", 0))
        line_end = int(citation.get("line_end", 0))
    except (TypeError, ValueError):
        reasons.append("invalid_line_range")
        tags.append("invalid_citation")
        return False, reasons, tags
    snippet = citation.get("snippet")
    if not isinstance(snippet, str) or not snippet.strip():
        reasons.append("missing_snippet")
        tags.append("invalid_citation")
        return False, reasons, tags
    excerpt = _extract_lines(path, line_start, line_end)
    if excerpt is None:
        reasons.append("line_range_out_of_bounds")
        tags.append("invalid_citation")
        return False, reasons, tags
    if _normalize(snippet) not in _normalize(excerpt):
        reasons.append("snippet_mismatch")
        tags.append("stale_memory")
        return False, reasons, tags
    if claim_text and _normalize(claim_text) not in _normalize(snippet):
        reasons.append("claim_mismatch")
        tags.append("contradicted_memory")
        return False, reasons, tags
    return True, reasons, tags


def verify_memory_entry(entry: dict[str, Any], *, root: Path) -> dict[str, Any]:
    entry_id = str(entry.get("id", "")).strip()
    used = bool(entry.get("used", True))
    claim_text = str(entry.get("claim_text", "")).strip()
    citations = entry.get("citations")
    confidence = entry.get("confidence")
    reasons: list[str] = []
    tags: list[str] = []
    citations_total = 0
    citations_ok = 0
    ok = True

    if not entry_id:
        reasons.append("missing_id")
        tags.append("invalid_citation")
        ok = False

    if not claim_text:
        reasons.append("missing_claim_text")
        tags.append("invalid_citation")
        ok = False

    if not isinstance(citations, list) or not citations:
        reasons.append("no_citations")
        tags.append("invalid_citation")
        ok = False
    else:
        for citation in citations:
            citations_total += 1
            if not isinstance(citation, dict):
                reasons.append("invalid_citation_type")
                tags.append("invalid_citation")
                ok = False
                continue
            ctype = str(citation.get("type", "repo")).strip().lower()
            if ctype != "repo":
                reasons.append(f"unsupported_citation_type:{ctype}")
                tags.append("invalid_citation")
                ok = False
                continue
            passed, c_reasons, c_tags = _verify_repo_citation(
                citation, root=root, claim_text=claim_text
            )
            if passed:
                citations_ok += 1
            else:
                ok = False
                reasons.extend(c_reasons)
                tags.extend(c_tags)

    if not ok and confidence is not None:
        try:
            if float(confidence) >= 0.8:
                tags.append("overconfident_memory")
        except (TypeError, ValueError):
            pass

    return {
        "id": entry_id or None,
        "used": used,
        "ok": ok,
        "reasons": sorted(set(reasons)),
        "tags": sorted(set(tags)),
        "citations_total": citations_total,
        "citations_ok": citations_ok,
    }


def verify_memory_entries(
    entries: list[dict[str, Any]], *, root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = [verify_memory_entry(entry, root=root) for entry in entries]
    total = len(results)
    used_results = [r for r in results if r.get("used", False)]
    used_total = len(used_results)
    verified = sum(1 for r in used_results if r.get("ok"))
    invalid = sum(1 for r in used_results if not r.get("ok"))

    tag_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for r in used_results:
        for tag in r.get("tags", []):
            tag_counts[tag] += 1
        for reason in r.get("reasons", []):
            reason_counts[reason] += 1

    use_rate = (used_total / total) if total else 0.0
    verified_rate = (verified / used_total) if used_total else 0.0
    invalid_rate = (invalid / used_total) if used_total else 0.0

    summary = {
        "memory_total": total,
        "memory_used_count": used_total,
        "memory_verified_count": verified,
        "memory_invalid_count": invalid,
        "memory_use_rate": use_rate,
        "memory_verified_rate": verified_rate,
        "memory_invalid_rate": invalid_rate,
        "actions_blocked_by_memory_gate": invalid,
        "memory_tag_counts": dict(sorted(tag_counts.items())),
        "memory_reason_counts": dict(sorted(reason_counts.items())),
    }
    return results, summary


def verify_memory_path(path: str | Path, *, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = list(read_jsonl(path))
    return verify_memory_entries(entries, root=root)
