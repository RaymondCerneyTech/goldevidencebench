from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Limit a JSONL file to N rows.")
    parser.add_argument("--in", dest="input_path", required=True, help="Input JSONL path.")
    parser.add_argument("--out", dest="output_path", required=True, help="Output JSONL path.")
    parser.add_argument("--max-rows", type=int, required=True, help="Maximum rows to keep.")
    args = parser.parse_args()

    input_path = Path(args.input_path)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")
    if args.max_rows <= 0:
        raise SystemExit("max-rows must be > 0")

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kept = []
    with input_path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if len(kept) >= args.max_rows:
                break
            line = line.strip()
            if not line:
                continue
            kept.append(line)

    output_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"Wrote {output_path} ({len(kept)} rows)")


if __name__ == "__main__":
    main()
