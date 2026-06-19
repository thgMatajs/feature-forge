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

    C-07b (PR18-R6): um `.claude/settings.json` editado à mão pode trazer
    `hooks` num shape inesperado (`"hooks": "x"`, `"hooks": []`) ou
    `hooks.<stage>` não-lista. Antes, `.setdefault`/`.append` estouravam
    AttributeError e derrubavam o init inteiro. Agora coercimos defensivamente:
    `hooks` não-dict → preserva o valor original sob `hooks.__forge_backup__` e
    trata como `{}`; `hooks.<stage>` não-lista → idem sob a chave de stage com
    sufixo `__forge_backup__`. O conteúdo do usuário nunca é perdido — só movido
    pra um campo de backup — e o merge segue.
    """
    result = deepcopy(existing)
    add_hooks = additions.get("hooks", {})
    res_hooks = result.get("hooks")
    if not isinstance(res_hooks, dict):
        if res_hooks is not None:
            # Preserva o valor não-dict sob backup antes de resetar.
            result["hooks"] = {"__forge_backup__": res_hooks}
        else:
            result["hooks"] = {}
        res_hooks = result["hooks"]
    for stage, entries in add_hooks.items():
        existing_entries = res_hooks.get(stage)
        if not isinstance(existing_entries, list):
            if existing_entries is not None:
                res_hooks[f"{stage}__forge_backup__"] = existing_entries
            existing_entries = []
            res_hooks[stage] = existing_entries
        for entry in entries:
            if entry not in existing_entries:
                existing_entries.append(entry)
    for k, v in additions.items():
        if k == "hooks":
            continue
        result.setdefault(k, v)
    return result


# JSON5 tolerance — comments + trailing commas in settings.json (Spec §3 C.4).
try:
    import json5  # type: ignore[import-not-found]
    _HAS_JSON5 = True
except ImportError:
    import json as json5  # type: ignore[no-redef]
    _HAS_JSON5 = False


def read_settings_tolerant(content: str) -> dict:
    """Parse settings.json content, tolerating JSON5 extensions if available.

    Real-world Claude Code users edit `.claude/settings.json` with comments
    and trailing commas — common JSON5 patterns. With json5 lib installed,
    we parse those gracefully; without it, falls back to stdlib json (strict).
    """
    return json5.loads(content)
