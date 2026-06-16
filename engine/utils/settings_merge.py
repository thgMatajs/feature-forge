"""Append-only merge for .claude/settings.json — preserves user-owned entries.

Spec §3 (C.4) — brownfield-safe init: forge MUST NOT overwrite hooks already
declared by the user. New forge hooks land alongside existing entries; identical
shape (deep-equal dict comparison) is silently deduplicated for idempotency.
"""
from copy import deepcopy
from typing import Any


def merge_settings_json(existing: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    """Merge `additions` INTO `existing` without overwriting user content.

    - dict keys: union; for `hooks.<stage>` (list type), append additions
    - top-level keys other than `hooks`: only add when absent in existing
    - dedupe identical entries via `entry not in existing_entries` (idempotent)
    """
    result = deepcopy(existing)
    add_hooks = additions.get("hooks", {})
    res_hooks = result.setdefault("hooks", {})
    for stage, entries in add_hooks.items():
        existing_entries = res_hooks.setdefault(stage, [])
        for entry in entries:
            if entry not in existing_entries:
                existing_entries.append(entry)
    for k, v in additions.items():
        if k == "hooks":
            continue
        result.setdefault(k, v)
    return result
