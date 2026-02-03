# Sample Artifacts (Pinned)

This folder contains a tiny, static artifact pack from a real bad_actor holdout failure run.
It lets you inspect the exact outputs without running anything.

Source run:
- runs/bad_actor_holdout_20260202_230442

Included files:
- report.md
- diagnosis.json
- summary.json
- repro_commands.json
- compact_state.json
- thread.jsonl

Notes:
- Paths inside these artifacts are Windows-style from the original run.
- The failure is intentional (unsafe-commit case, action_safety bottleneck); your current gates may now pass.
