"""Detect host com precedence: config > env > fallback intent_file. Spec §2."""
import sys
from pathlib import Path
from functools import lru_cache
import yaml
from engine.host.adapter import HostName
from engine.host import env

_cache: dict[Path, HostName] = {}


def _clear_cache() -> None:
    _cache.clear()


def _read_config_host(project_root: Path) -> HostName | None:
    cfg = project_root / ".claude" / "forge" / "forge-config.yaml"
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text()) or {}
    except yaml.YAMLError:
        return None
    h = data.get("host")
    if not h:
        return None
    try:
        return HostName(h)
    except ValueError:
        return None


def detect_host(project_root: Path) -> HostName:
    if project_root in _cache:
        return _cache[project_root]
    # 1. Config override (forge-config.yaml `host:` vence tudo)
    cfg = _read_config_host(project_root)
    if cfg is not None:
        result = cfg
    # 2. Escape-hatch explícito do usuário avançado — drift-1 spec §439.
    #    Preservado pós-clean-break (W2 removeu tty_bridge mas mantém o
    #    escape-hatch).  Vence auto-detect de env/isatty, mas NÃO vence
    #    config explícito (bloco acima).
    elif env._truthy("FORGE_FORCE_INTENT_MODE"):
        result = HostName.INTENT_FILE
    # 3. Env scan
    elif env.detect_claude_code():
        result = HostName.CLAUDE_CODE
    elif env.detect_opencode():
        result = HostName.OPENCODE
    # 4. TTY check (humano em terminal real)
    elif sys.stdin.isatty():
        result = HostName.TTY
    # 5. Fallback
    else:
        result = HostName.INTENT_FILE
    _cache[project_root] = result
    return result
