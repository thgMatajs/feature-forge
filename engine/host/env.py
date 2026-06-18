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


# A3 ENV-1 — key-set canônico de sinais de host agêntico. Alinhado a
# tests/unit/test_cli_upgrade_wired.py (_SCRUB_EXACT / _SCRUB_PREFIXES) e aos
# detectores acima. EXATAS: comparação por igualdade. PREFIXES: startswith.
_SCRUB_EXACT: frozenset[str] = frozenset({
    "CLAUDECODE",
    "FORGE_FORCE_INTENT_MODE",
    "FORGE_FORCE_TTY_MODE",
})
_SCRUB_PREFIXES: tuple[str, ...] = ("OPENCODE_", "CODEX", "CURSOR_")


def _is_agentic_host_key(name: str) -> bool:
    """True se ``name`` é um sinal de host agêntico que um subprocesso filho
    NÃO deve herdar."""
    if name in _SCRUB_EXACT:
        return True
    return any(name.startswith(p) for p in _SCRUB_PREFIXES)


def scrubbed_subprocess_env() -> dict[str, str]:
    """Cópia de ``os.environ`` sem os sinais de host agêntico.

    A3 ENV-1: quando o forge spawna um subprocesso (ex.: validators via
    ``engine.ingest``), o filho não deve herdar CLAUDECODE / OPENCODE_* /
    CODEX* / CURSOR_* / FORGE_FORCE_*_MODE. Caso contrário, um ``forge``
    aninhado faria ``detect_host`` escolher um adapter agêntico, emitir o
    marker ``<FORGE_INTENT/>`` + exit 2, e esperar um driver que aquele
    contexto não tem — travando (hang).

    Deny-list cirúrgica (remove só os sinais de host) — distinta de
    ``engine._sandbox.env.build_safe_env``, que é uma allowlist agressiva pra
    a sandbox de QA (objetivo: conter segredos). Os dois coexistem por terem
    objetivos diferentes; aqui preservamos PATH/HOME/JAVA_HOME/etc. que um
    validator de ingest precisa.

    Não muta ``os.environ`` — retorna cópia.
    """
    return {k: v for k, v in os.environ.items() if not _is_agentic_host_key(k)}
