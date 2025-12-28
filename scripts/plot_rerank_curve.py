import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in-csv",
        type=Path,
        default=Path("runs/summary_all.csv"),
        help="Input summary_all.csv path.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/figures/rerank_k_curve_s5q24.png"),
        help="Output image path.",
    )
    parser.add_argument(
        "--metric",
        type=str,
        default="selection_rate",
        choices=("selection_rate", "accuracy_when_gold_present", "value_acc"),
        help="Metric to plot.",
    )
    return parser.parse_args()


def load_series(rows, prefix):
    series = {}
    for row in rows:
        run_name = row.get("run_name", "")
        if not run_name.startswith(prefix):
            continue
        try:
            k = int(run_name.split("_k")[1].split("_")[0])
            series[k] = float(row.get(metric, 0.0))
        except (IndexError, ValueError, TypeError):
            continue
    return series


def main() -> int:
    args = parse_args()
    rows = []
    with args.in_csv.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    global metric
    metric = args.metric

    none = load_series(rows, "ab_rerank_none_k")
    latest = load_series(rows, "ab_rerank_latest_step_k")

    if not none or not latest:
        raise SystemExit("Missing rerank series in summary_all.csv (need ab_rerank_none_k* and ab_rerank_latest_step_k*).")

    ks = sorted(set(none) & set(latest))
    none_vals = [none[k] for k in ks]
    latest_vals = [latest[k] for k in ks]

    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    ax.plot(ks, none_vals, marker="o", label="none")
    ax.plot(ks, latest_vals, marker="o", label="latest_step")
    ax.set_xticks(ks)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("k (candidates)")
    ax.set_ylabel(args.metric)
    ax.set_title("Reranker k-curve (same_key, shuffle, s5q24)")
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend(frameon=False)
    fig.tight_layout()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=200)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
