"""Env var helpers pra detect host agentic. Spec §2 / §4."""
import os


def _truthy(varname: str) -> bool:
    val = os.environ.get(varname)
    return bool(val) and val.lower() not in {"0", "false", "no", ""}


def detect_claude_code() -> bool:
    return _truthy("CLAUDECODE")


def detect_opencode() -> bool:
    # opencode setta vars com prefixo OPENCODE_
    return any(k.startswith("OPENCODE_") for k in os.environ.keys())


def detect_codex() -> bool:
    return any(k.startswith("CODEX") for k in os.environ.keys())


def detect_cursor() -> bool:
    return _truthy("CURSOR_AGENT") or any(k.startswith("CURSOR_") for k in os.environ.keys())


def detect_any_agentic() -> bool:
    return detect_claude_code() or detect_opencode() or detect_codex() or detect_cursor()
