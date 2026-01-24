from __future__ import annotations

import argparse
import json
from pathlib import Path

from goldevidencebench import drift as drift_mod
from goldevidencebench import walls


def main() -> int:
    parser = argparse.ArgumentParser(description="Find a drift wall from summary.json runs.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--metric", dest="metric_path", default="drift.step_rate")
    parser.add_argument("--param", dest="param_key", default="steps")
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--direction", choices=["gte", "lte"], required=True)
    parser.add_argument("--state-mode", type=str, default=None)
    parser.add_argument("--profile", type=str, default=None)
    parser.add_argument("--aggregate", choices=["none", "max", "min"], default="max")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--update-config", type=Path, default=None)
    parser.add_argument("--check-id", type=str, default=None)
    parser.add_argument("--metric-path", dest="config_metric_path", type=str, default=None)
    args = parser.parse_args()

    points = walls.load_points(
        runs_dir=args.runs_dir,
        metric_path=args.metric_path,
        param_key=args.param_key,
        state_mode=args.state_mode,
        distractor_profile=args.profile,
    )
    if not points:
        print("No matching runs found.")
        return 1
    if args.aggregate != "none":
        points = walls.aggregate_points(points, mode=args.aggregate)
    points = sorted(points, key=lambda p: p.param)

    last_ok, wall = drift_mod.find_drift_wall(
        points, threshold=args.threshold, direction=args.direction
    )
    payload = drift_mod.wall_payload(
        points=points,
        metric_path=args.metric_path,
        param_key=args.param_key,
        threshold=args.threshold,
        direction=args.direction,
        state_mode=args.state_mode,
        distractor_profile=args.profile,
        last_ok=last_ok,
        wall=wall,
    )
    out_path = args.out or (args.runs_dir / "drift_wall.json")
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    if wall:
        print(f"wall_param={wall.param:.4f} wall_metric={wall.metric:.4f} run_dir={wall.run_dir}")
    else:
        print("wall_param=None")
    if last_ok:
        print(f"last_ok_param={last_ok.param:.4f} last_ok_metric={last_ok.metric:.4f} run_dir={last_ok.run_dir}")

    if args.update_config:
        if not args.check_id:
            raise SystemExit("--check-id is required with --update-config")
        metric_path = args.config_metric_path or args.metric_path
        walls.update_threshold_config(
            config_path=args.update_config,
            check_id=args.check_id,
            metric_path=metric_path,
            threshold=args.threshold,
            direction=args.direction,
        )
        print(f"Updated {args.update_config} ({args.check_id} {metric_path})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
