from __future__ import annotations

import sys

from check_control_family_reliability import main_for_family


if __name__ == "__main__":
    raise SystemExit(main_for_family("persona_amalgamation", sys.argv[1:]))
