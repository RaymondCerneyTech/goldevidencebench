from __future__ import annotations

import sys

from generate_control_family_scaffold import main_for_family


if __name__ == "__main__":
    raise SystemExit(main_for_family("noise_escalation", sys.argv[1:]))
