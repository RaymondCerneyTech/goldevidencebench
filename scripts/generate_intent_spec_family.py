from __future__ import annotations

import sys

from generate_control_family_scaffold import main_for_family


if __name__ == "__main__":
    raise SystemExit(main_for_family("intent_spec_layer", sys.argv[1:]))
