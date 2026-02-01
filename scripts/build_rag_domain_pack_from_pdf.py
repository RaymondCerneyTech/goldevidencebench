from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
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


def _tweak_line(line: str, *, delta: int, prefix: str) -> str:
    match = re.search(r"\d[\d,]*", line)
    if match:
        raw = match.group(0)
        num = int(raw.replace(",", ""))
        num = max(0, num + delta)
        replacement = str(num)
        return f"{line[:match.start()]}{replacement}{line[match.end():]}"
    return f"{prefix} {line}"


def _build_entries(lines: list[str], max_entries: int, stale_frac: float, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed)
    if len(lines) <= max_entries:
        selected = lines
    else:
        selected = rng.sample(lines, max_entries)
    stale_count = max(1, int(len(selected) * stale_frac))
    entries: list[dict[str, str]] = []
    for idx, line in enumerate(selected):
        words = line.split()
        label = " ".join(words[:6]).rstrip(".,;:")
        entry_id = f"IRS{idx + 1:03d}-Q001"
        episode = f"IRS{idx + 1:03d}"
        key = f"irs.{idx:03d}"
        policy = line
        current = line
        if idx < stale_count:
            old = _tweak_line(line, delta=-1, prefix="Previous")
            decoy = _tweak_line(line, delta=1, prefix="Draft")
            bucket = "stale_doc"
        else:
            old = None
            decoy = _tweak_line(line, delta=2, prefix="Draft")
            bucket = "authority_decoy"
        entries.append(
            {
                "id": entry_id,
                "episode": episode,
                "key": key,
                "label": label or entry_id,
                "policy": policy,
                "current": current,
                "old": old,
                "decoy": decoy,
                "bucket": bucket,
            }
        )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Build domain pack fixtures from a PDF.")
    parser.add_argument("--pdf-path", required=True, help="Path to a PDF to ingest.")
    parser.add_argument("--out-dir", required=True, help="Output directory for the pack.")
    parser.add_argument("--max-entries", type=int, default=16, help="Number of fixtures to build.")
    parser.add_argument("--min-line-len", type=int, default=30, help="Minimum line length.")
    parser.add_argument("--max-line-len", type=int, default=120, help="Maximum line length.")
    parser.add_argument("--stale-frac", type=float, default=0.5, help="Fraction of stale_doc entries.")
    parser.add_argument("--seed", type=int, default=13, help="Random seed for sampling lines.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = _extract_lines(pdf_path)
    candidates = _filter_lines(lines, args.min_line_len, args.max_line_len)
    if not candidates:
        raise SystemExit("No suitable lines extracted from PDF.")

    entries = _build_entries(candidates, args.max_entries, args.stale_frac, args.seed)
    entries_path = out_dir / "domain_entries.jsonl"
    entries_path.write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
        encoding="utf-8",
    )

    build_script = Path("scripts") / "build_rag_domain_pack.py"
    result = subprocess.run(
        [sys.executable, str(build_script), "--in", str(entries_path), "--out-dir", str(out_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise SystemExit("Failed to build domain pack from PDF.")

    print(f"Wrote {out_dir / 'rag_domain_stale.jsonl'}")
    print(f"Wrote {out_dir / 'rag_domain_authority.jsonl'}")


if __name__ == "__main__":
    main()
