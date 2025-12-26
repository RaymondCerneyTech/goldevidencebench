from __future__ import annotations

import argparse
import json
from pathlib import Path


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate sweep runtime.")
    parser.add_argument("--seeds", type=int, required=True)
    parser.add_argument("--episodes", type=int, required=True)
    parser.add_argument("--queries", type=int, required=True)
    parser.add_argument("--state-modes", type=int, required=True, help="Count of state modes in the sweep.")
    parser.add_argument("--distractor-profiles", type=int, required=True, help="Count of distractor profiles.")
    parser.add_argument("--twins", action="store_true", help="If set, double the query count.")
    parser.add_argument("--seconds-per-q", type=float, default=30.0)
    parser.add_argument("--from-combined", type=Path, default=None, help="Path to combined.json to estimate seconds-per-q.")
    args = parser.parse_args()

    if args.from_combined:
        try:
            rows = json.loads(Path(args.from_combined).read_text(encoding="utf-8"))
            per_q = [r.get("efficiency", {}).get("wall_s_per_q") for r in rows]
            per_q = [p for p in per_q if isinstance(p, (int, float))]
            avg = _mean(per_q)
            if avg is not None:
                args.seconds_per_q = avg
        except Exception:
            pass

    multiplier = 2 if args.twins else 1
    total_q = args.seeds * args.episodes * args.queries * args.state_modes * args.distractor_profiles * multiplier
    total_s = total_q * args.seconds_per_q
    hours = total_s / 3600.0
    mins = total_s / 60.0
    print(f"questions={total_q}")
    print(f"seconds={total_s:.0f}")
    print(f"minutes={mins:.1f}")
    print(f"hours={hours:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
