"""Detect host com precedence: config > env > fallback intent_file. Spec §2."""
import sys
from pathlib import Path
from functools import lru_cache
import yaml
from engine.host.adapter import HostName
from engine.host import env
from engine.utils.paths import active_config_path

_cache: dict[Path, HostName] = {}


def _clear_cache() -> None:
    _cache.clear()


def _read_config_host(project_root: Path) -> HostName | None:
    # C-10 (CL-A): usa active_config_path (Mandamento 3) — primário
    # .claude/forge/forge-config.yaml com fallback legado
    # .claude/workflow-config.yaml. Antes hardcodava só o primário → projetos
    # v1.2 com host: no legado eram ignorados.
    cfg = active_config_path(project_root)
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
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
        # Ramo aspiracional: só alcançado se o env carregar OPENCODE_* — raro
        # hoje, pois o opencode não injeta essas vars em subprocessos
        # (docs/research/opencode-tool-api.md §3). No caso comum, opencode
        # não dispara aqui e cai no fallback TTY→INTENT_FILE abaixo.
        result = HostName.OPENCODE
    # 4. TTY check (humano em terminal real)
    elif sys.stdin.isatty():
        result = HostName.TTY
    # 5. Fallback
    else:
        result = HostName.INTENT_FILE
    _cache[project_root] = result
    return result
