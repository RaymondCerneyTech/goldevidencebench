from __future__ import annotations

from goldevidencebench.adapters.external_cli_adapter import ExternalCliAdapter
from goldevidencebench.util import get_env


def create_adapter() -> ExternalCliAdapter:
    """
    Thin wrapper around ExternalCliAdapter for Vulkan/llama.cpp CLI usage.

    Set:
      - GOLDEVIDENCEBENCH_VULKAN_CMD (CLI template with {prompt} or {prompt_file})
    """
    cmd_template = get_env("VULKAN_CMD")
    if not cmd_template:
        raise ValueError(
            "Set GOLDEVIDENCEBENCH_VULKAN_CMD to a CLI template (use {prompt} or {prompt_file})."
        )
    return ExternalCliAdapter(cmd_template=cmd_template)
