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
    """Detecção aspiracional / não-wirada em ``detect_host`` (DETECT-1).

    Paralela a ``detect_opencode``: future-proofing pra um host codex futuro.
    ``detect_host`` NÃO consulta esta função — codex cai no fallback
    TTY→INTENT_FILE como qualquer host sem detector dedicado. Mantida (a) como
    future-proofing e (b) como superfície de verificação do scrub ENV-1.

    C-49b (PR22-B-02): a DETECÇÃO usa o prefixo preciso ``CODEX_`` (o codex
    injeta ``CODEX_CLI`` etc.) — ``CODEX`` cru casaria falsos-positivos como
    ``CODEXBASE``/``CODEX_UNRELATED`` de outros tools. O SCRUB
    (``_SCRUB_PREFIXES``) permanece deliberadamente mais largo (``CODEX``):
    scrub é defesa — varrer um ``CODEX`` cru a mais é inócuo, deixar um
    ``CODEX_CLI`` passar não é. Eixos com objetivos distintos: detector =
    preciso, scrub = abrangente.
    """
    return any(k.startswith("CODEX_") for k in os.environ.keys())


def detect_cursor() -> bool:
    """Detecção aspiracional / não-wirada em ``detect_host`` (DETECT-1).

    Mesmo contrato de ``detect_codex``: future-proofing + superfície de
    verificação do scrub ENV-1 (``_SCRUB_PREFIXES`` carrega ``CURSOR_``). Não
    consultada por ``detect_host``.
    """
    return _truthy("CURSOR_AGENT") or any(k.startswith("CURSOR_") for k in os.environ.keys())


# A3 ENV-1 — key-set canônico de sinais de host agêntico. Alinhado a
# tests/unit/test_cli_upgrade_wired.py (_SCRUB_EXACT / _SCRUB_PREFIXES) e aos
# detectores acima. EXATAS: comparação por igualdade. PREFIXES: startswith.
_SCRUB_EXACT: frozenset[str] = frozenset({
    "CLAUDECODE",
    "FORGE_FORCE_INTENT_MODE",
    # C-27 (PR20-R5): ``FORGE_FORCE_TTY_MODE`` é INERTE em ``detect_host`` (não
    # há branch que o consulte — só ``FORGE_FORCE_INTENT_MODE`` tem). Mantido no
    # scrub mesmo assim: defesa barata (varrer uma var inerte é inócuo) e evita
    # que um subprocesso herde um override fantasma se um branch TTY-force vier
    # a existir. Marcado inerte aqui pra não confundir um leitor futuro.
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

    C-24 (PR20-R3): este scrub cobre só os sinais de host DERIVADOS DO ENV
    (CLAUDECODE / OPENCODE_* / CODEX* / CURSOR_*). NÃO neutraliza um
    ``host:`` setado explicitamente em ``forge-config.yaml`` — esse override de
    config tem precedência sobre o env scan em ``detect_host`` (passo 1) e
    sobrevive a este scrub. Um subprocesso filho num projeto com ``host:`` no
    config ainda resolveria aquele host. O scrub previne herança ACIDENTAL de
    env agêntico, não override DELIBERADO de config — escopos distintos.

    Não muta ``os.environ`` — retorna cópia.
    """
    return {k: v for k, v in os.environ.items() if not _is_agentic_host_key(k)}
