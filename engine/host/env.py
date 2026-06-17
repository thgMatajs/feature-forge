"""Env var helpers pra detect host agentic. Spec §2 / §4."""
import os


def _truthy(varname: str) -> bool:
    val = os.environ.get(varname)
    return bool(val) and val.lower() not in {"0", "false", "no", ""}


def detect_claude_code() -> bool:
    return _truthy("CLAUDECODE")


def detect_opencode() -> bool:
    # Detecção aspiracional / atualmente inativa na prática.
    #
    # A checagem por prefixo OPENCODE_ é best-effort/future-proofing: o
    # projeto reconhece opencode como host futuro conhecido (Veredito B do
    # research), mas hoje este ramo quase nunca dispara. Conforme
    # docs/research/opencode-tool-api.md §3, o opencode NÃO injeta vars
    # OPENCODE_* nos subprocessos que ele spawna — o bash tool herda
    # process.env, mas o próprio opencode não setta uma var identificadora
    # estável (issue sst/opencode#1775 regrediu). Logo, um subprocesso forge
    # invocado pelo opencode normalmente NÃO vê nenhum OPENCODE_* no env.
    #
    # Na prática, opencode resolve via fallback TTY→INTENT_FILE: stdin é
    # pipado (não-tty), então detect_host cai em HostName.INTENT_FILE — o
    # comportamento documentado. Mantemos esta função como future-proofing;
    # revisitar quando/se opencode shippar elicitation ou env var confiável.
    return any(k.startswith("OPENCODE_") for k in os.environ.keys())


def detect_codex() -> bool:
    return any(k.startswith("CODEX") for k in os.environ.keys())


def detect_cursor() -> bool:
    return _truthy("CURSOR_AGENT") or any(k.startswith("CURSOR_") for k in os.environ.keys())


def detect_any_agentic() -> bool:
    return detect_claude_code() or detect_opencode() or detect_codex() or detect_cursor()
