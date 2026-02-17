from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from goldevidencebench.state_store import create_state_store


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Micro-benchmark for StateStore backends.")
    parser.add_argument(
        "--backend",
        choices=("current", "sparse_set"),
        default="current",
    )
    parser.add_argument("--ops", type=int, default=20000)
    parser.add_argument("--keys", type=int, default=400)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    ns = _parse_args()
    store = create_state_store(ns.backend)

    key_count = max(1, ns.keys)
    ops = max(1, ns.ops)
    start = time.perf_counter()
    for step in range(ops):
        key = f"key.{step % key_count:03d}"
        if step % 7 == 0:
            store.clear(key)
        else:
            store.set(key, f"value_{step}")
    elapsed = time.perf_counter() - start
    active = store.list_active()
    result = {
        "backend": store.backend,
        "experimental": store.experimental,
        "ops": ops,
        "keys": key_count,
        "elapsed_s": elapsed,
        "ops_per_s": (ops / elapsed) if elapsed > 0 else 0.0,
        "active_count": len(active),
        "event_count": len(store.events()),
    }
    print(json.dumps(result, indent=2))
    if ns.out is not None:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
