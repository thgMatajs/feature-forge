---
title: QA-11 sandbox env hardening — allowlist core + per-card opt-in
date: 2026-06-08
status: design-approved (awaiting implementation plan)
revisita: nenhuma decisão locked (gap QA-11 estava marcado open pendente brainstorm)
---

# QA-11 sandbox env hardening — allowlist core + per-card opt-in

> **Tipo:** brainstorming spec (origem: `superpowers:brainstorming`).
> **Data:** 2026-06-08.
> **Status:** design aprovado pelo usuário, aguardando `superpowers:writing-plans` pra gerar plano executável.
> **Resolve:** Gap QA-11 (`docs/design/04-pending.md` linhas 1933-1953) — sandbox subprocess herda env completo via `env = dict(os.environ)` em `engine/qa/sandbox.py:157`.
> **Bloqueador pré-piloto:** sim — último crítico do `forge qa` antes de pilotar em projeto real (junto com QA-13 que é fix menor separado).

## §1. Resumo executivo

O sandbox subprocess do `forge qa` Phase 3 (`engine/qa/sandbox.py:157`)
hoje constrói o env do filho via `env = dict(os.environ)`. Isso significa
que qualquer secret presente no processo pai — `AWS_TOKEN`, `GITHUB_TOKEN`,
`DB_PASSWORD`, `*_SECRET`, padrões equivalentes — entra inteiro no
subprocess que roda validators contra fixtures sintéticos. Em pilot real
o risco é concreto em duas direções: card extension (`qa-extensions.auditors`
apontando pra script terceiro) que lê `os.environ` e captura o secret em
`finding.evidence` ou stderr; ou vazamento acidental em traceback/log de
validator canon que printa env durante debug.

A defesa proposta é híbrida e mínima: allowlist core hardcoded com o
conjunto provado necessário pra validators canon (`grep os.environ
validators/` = vazio confirma que canon não consome env diretamente),
mais opt-in declarativo por card via `qa-extensions.env-needs`, mais
grant explícito do user pra vars que batem pattern sensitive — esse grant
persiste em `workflow-config.qa.sensitive-env-grants` (per-projeto, não
per-card, KISS).

Escopo do refactor: helper compartilhado em `engine/_sandbox/env.py`,
consumido tanto por `engine.qa.sandbox` quanto por `engine.verify`
(linha 624 também faz subprocess sem `env=`; promote-to-shared agora
evita drift futuro, Q13). Out-of-scope v1: subprocess wrapper de alto
nível, context manager `with safe_env():`, property-based testing
com hypothesis.

## §2. Motivação

Quatro razões pra agir agora, todas verificáveis:

**Verificação concreta de feasibility.** `grep -rn "os.environ"
validators/` retorna vazio. Os 15 validators canon não dependem de env
vars diretamente — só usam o que o Python implicitamente precisa (PATH
pra binary lookup, HOME pra ~ expansion, LANG pra unicode em pytest
output). Isso permite allowlist agressiva sem quebrar canon. Validar
isso experimentalmente é cheap: roda `forge verify` com env mínimo, vê
se passa, ajusta CORE_ALLOWLIST se algo essential aparecer.

**Threat model dual com defesa unificada.** O risco é card extension
malicioso (ator intencional via `qa-extensions.auditors`) E vazamento
acidental em validator canon (acidente comum em pilot — `traceback` que
printa locals, debug log esquecido). Diferenciar canon-vs-extension
boundary na defesa seria caro arquiteturalmente e ganho marginal —
defesa única (env reduzido pro subprocess) cobre os dois com mesma
mecânica.

**Promote-to-shared evita drift futuro.** `engine/verify.py:624` tem o
mesmo bug hoje: `subprocess.run(...)` sem `env=`. O Python default
nesse caso é herdar env do pai — mesma janela de leak. Extrair helper
compartilhado agora (Q13 reuse-intelligence: "promote-to-shared") é
mais barato que duplicar a lógica e converger no V2.

**Defesa não pode erodir por config silenciosa.** Análogo ao Gap QA-6
(custom rubric per project foi rejeitado pelo mesmo motivo): permitir
override irrestrito via workflow-config simples erodiria o gate. A
escolha aqui é forçar prompt + grant explícito do user no momento de
ativar card que pede sensitive var — mantém o gate audível e revisável.

## §3. Threat model

| Cenário | Defesa |
|---|---|
| Card extension malicioso declara auditor que faz `os.environ['AWS_TOKEN']` no subprocess | Subprocess recebe env reduzido ao allowlist core; `AWS_TOKEN` não está lá; lookup retorna `None`; secret não vaza. |
| Vazamento acidental em validator canon que printa env em traceback de debug (`print(os.environ)` esquecido) | Var sensitive não existe no env do subprocess; nada pra printar; stderr fica limpo. |
| Card legítimo declara `env-needs: [GITHUB_TOKEN]` (var bate pattern sensitive) | `forge init`/`forge reconfigure` dispara prompt 3-caminhos exigindo grant explícito; sem grant, card é desativado pra esse projeto. |
| Card legítimo declara `env-needs: [JAVA_HOME]` (var non-sensitive) | Passa direto, sem prompt; user instalou o card (trust chain mínimo), var não bate pattern sensitive, é injetada no extras do subprocess sem fricção. |

## §4. Arquitetura

**Novo módulo:** `engine/_sandbox/env.py`, num subpacote novo
`engine/_sandbox/` com `__init__.py`. O underscore-prefix sinaliza
internal API — consumidores são `engine.qa.sandbox`, `engine.verify`,
`engine.qa.__init__`, `engine.cards.loader`, `engine.cards.grant`,
`engine.init`, `engine.reconfigure`; externos não devem importar.
Pure stdlib (`re`, `os`) — zero dep em `engine.*` pra evitar ciclo
de import com `engine.qa` ou `engine.cards`.

**API pública (3 símbolos + 2 constantes):**

- `build_safe_env(*, extras: Iterable[str] = ()) -> dict[str, str]` —
  retorna dict pronto pra `subprocess.run(..., env=...)`, com
  `CORE_ALLOWLIST ∪ extras` filtradas contra `os.environ`.
- `inspect_dropped(*, extras: Iterable[str] = ()) -> list[str]` —
  retorna lista ordenada das vars que existem em `os.environ` mas não
  entrariam no env do filho. Usada pra alert pré Phase 3.
- `is_sensitive(name: str) -> bool` — testa `name` contra
  `SENSITIVE_PATTERN`. Usada por `engine.cards.grant` pra decidir se
  declared `env-need` exige prompt.
- `CORE_ALLOWLIST: frozenset[str]` — vars whitelisted sempre.
- `SENSITIVE_PATTERN: re.Pattern` — regex case-insensitive pra detecção
  de nomes "perigosos".

**Consumidores:**

- `engine.qa.sandbox._hardened_env` — refactor; recebe `extras` do
  caller, delega pra `build_safe_env`, adiciona PYTHONPATH com
  `guard_dir` e marker `FORGE_QA_SANDBOX=1`.
- `engine.verify` linha 624 — patch mínimo: adiciona
  `env=build_safe_env()` no `subprocess.run(...)`. Sem `extras` (verify
  não tem cards extension hoje).
- `engine.qa.__init__` — alert layer pré Phase 3: chama
  `inspect_dropped(extras=card_env_needs)`, filtra resultado por
  `is_sensitive`, se non-empty dispara `mentor_calm_three_paths` (ignore
  / declare no card / grant no projeto).
- `engine.cards.loader` — parse de `qa-extensions.env-needs` (lista
  opcional de strings) em `Card.env_needs` e `Card.sensitive_env_needs`.
- `engine.init` + `engine.reconfigure` — chamam
  `engine.cards.grant.evaluate_sensitive_grants` quando cards são
  ativados; orquestram prompt 3-caminhos e persistem grants em
  `workflow-config.qa.sensitive-env-grants`.

**`CORE_ALLOWLIST` proposta:**

```python
CORE_ALLOWLIST: frozenset[str] = frozenset({
    "PATH",                              # binary lookup defensivo
    "HOME",                              # ~ expansion + cache
    "USER", "LOGNAME",                   # subprocess identity
    "LANG", "LC_ALL", "LC_CTYPE",        # unicode em pytest output
    "TZ",                                # timestamps determinísticos
    "TMPDIR", "TEMP", "TMP",             # temp file creation
    "PYTHONHASHSEED",                    # determinismo dict ordering
})
```

**`SENSITIVE_PATTERN` proposta:**

```python
SENSITIVE_PATTERN: re.Pattern = re.compile(
    r"(?i).*(TOKEN|SECRET|PASSWORD|AUTH|CREDENTIAL|API[_-]?KEY|PRIVATE[_-]?KEY).*"
)
```

Case-insensitive (`(?i)`), tolerante a prefixo/sufixo (`.*…*`). Cobre
`GITHUB_TOKEN`, `aws_secret_access_key`, `MY_API_KEY`, `MY-API-KEY`,
`DB_PASSWORD`, `OAUTH2_CREDENTIAL`, `RSA_PRIVATE_KEY`.

## §5. Data flow

### 5.1 Boot de `forge qa` (Phase 3 sandbox)

```
engine/qa/__init__.py
  run_qa(scope, ...)
    └─> phase_3_sandbox(run_dir, fixtures, cards)
         ├─ card_env_needs = union(c.env_needs for c in cards)
         ├─ granted = workflow_config.qa.sensitive_env_grants   # list[str]
         ├─ allowed_extras = card_env_needs ∩ (CORE_ALLOWLIST ∪ granted)
         │                   ^-- vars declared pelos cards que estão
         │                       autorizadas (no core ou no grant)
         ├─ dropped = inspect_dropped(extras=allowed_extras)
         ├─ sensitive_dropped = [v for v in dropped if is_sensitive(v)]
         ├─ if sensitive_dropped:
         │     _alert_sensitive_drops(sensitive_dropped, card_env_needs)
         │     # mentor_calm_three_paths → user choice
         │
         └─> engine/qa/sandbox.run_sandbox(
                 run_dir, fixtures,
                 extras=allowed_extras,
             )
              └─ env = _hardened_env(guard_dir, extras=allowed_extras)
                   └─ base = build_safe_env(extras=allowed_extras)
                   └─ base["PYTHONPATH"] = guard_dir [+ existing]
                   └─ base["FORGE_QA_SANDBOX"] = "1"
                   └─ return base
              └─ subprocess.run(..., env=env, cwd=...)  per fixture
```

### 5.2 Boot de `forge verify`

```
engine/verify.py
  run_verify(...)
    └─> per validator spec:
         env = build_safe_env(extras=())
         subprocess.run(
             [sys.executable, str(spec.script_path), "--project-root", ...],
             env=env,
             check=False, capture_output=True, timeout=60,
         )
```

Sem `inspect_dropped` + alert: verify não roda untrusted code (cards
extension não entram em verify cascade hoje), alert vira ruído. Decisão
revisitável quando cards extension entrarem em verify (gap opt-in
explícito anotado em §9).

### 5.3 Card activation com sensitive var (forge init / reconfigure)

```
engine/init._activate_cards(card_names)
  └─ cards = [loader.load_card(p) for p in card_paths]
  └─ engine/cards/grant.evaluate_sensitive_grants(cards, workflow_config)
       ├─ por card c em cards:
       │    new_sensitive = c.sensitive_env_needs - workflow_config.granted
       │    if not new_sensitive: continue   # já granted
       │    for var in new_sensitive:
       │        decision = surface_three_paths(
       │            card=c, var=var,
       │            paths=[
       │                "grant"  → adiciona em workflow_config.granted,
       │                "deny"   → card desativado pra esse projeto,
       │                "abort"  → raise UserAbortError,
       │            ],
       │        )
       │        apply(decision)
       └─ persist workflow_config se grants mudaram
```

Grants são per-projeto (não per-card): se card A grant `GITHUB_TOKEN`,
card B usa mesmo grant sem novo prompt. KISS conforme decisão
brainstorm.

### 5.4 Não-fluxos (explicit)

- **Não há fallback "build_safe_env falhou → uso dict(os.environ)".**
  Hard fail (silencioso vira leak). Se algo quebrar em
  `build_safe_env`, raise propaga; subprocess não roda.
- **Não há flag `--unsafe-env`.** Viola Decisão 10 (zero-flags). Se
  user precisa override pontual, declara `env-needs` no card +
  grant — fluxo audível.
- **Não há per-fixture env.** Todas fixtures de um run compartilham
  o env do sandbox. YAGNI; nunca observado caso de uso.

## §6. API / Componentes (assinaturas exatas)

### `engine/_sandbox/env.py` (novo)

```python
"""Safe env builder pra subprocess. Allowlist core + extras declarados.

Internal API (underscore prefix). Consumidores autorizados:
- engine.qa.sandbox
- engine.verify
- engine.qa.__init__   (alert layer)
- engine.cards.loader  (parse env-needs)
- engine.cards.grant   (decisão sensitive)

Externos NÃO devem importar.
"""

from __future__ import annotations

import os
import re
from typing import Iterable


CORE_ALLOWLIST: frozenset[str] = frozenset({
    "PATH",                              # binary lookup defensivo
    "HOME",                              # ~ expansion + cache
    "USER", "LOGNAME",                   # subprocess identity
    "LANG", "LC_ALL", "LC_CTYPE",        # unicode em pytest output
    "TZ",                                # timestamps determinísticos
    "TMPDIR", "TEMP", "TMP",             # temp file creation
    "PYTHONHASHSEED",                    # determinismo dict ordering
})


SENSITIVE_PATTERN: re.Pattern = re.compile(
    r"(?i).*(TOKEN|SECRET|PASSWORD|AUTH|CREDENTIAL|API[_-]?KEY|PRIVATE[_-]?KEY).*"
)


def build_safe_env(*, extras: Iterable[str] = ()) -> dict[str, str]:
    """Constrói env reduzido pra subprocess.

    Retorna dict com (CORE_ALLOWLIST ∪ extras) ∩ os.environ. Vars
    listadas em ``extras`` mas ausentes em ``os.environ`` são filtradas
    silenciosamente (subprocess naturalmente não as vê).

    Raises
    ------
    TypeError
        Se algum elemento de ``extras`` não for ``str``.
    """
    allowed = CORE_ALLOWLIST | _validate_extras(extras)
    return {k: v for k, v in os.environ.items() if k in allowed}


def inspect_dropped(*, extras: Iterable[str] = ()) -> list[str]:
    """Retorna lista ordenada de vars em os.environ que seriam dropadas.

    Útil pra alert layer pré Phase 3: caller filtra por ``is_sensitive``
    pra decidir se dispara prompt.
    """
    allowed = CORE_ALLOWLIST | _validate_extras(extras)
    return sorted(k for k in os.environ if k not in allowed)


def is_sensitive(name: str) -> bool:
    """Testa nome contra SENSITIVE_PATTERN (case-insensitive)."""
    return SENSITIVE_PATTERN.match(name) is not None


def _validate_extras(extras: Iterable[str]) -> frozenset[str]:
    """Type-check + freeze. TypeError se houver não-string."""
    out: set[str] = set()
    for v in extras:
        if not isinstance(v, str):
            raise TypeError(
                f"build_safe_env extras: expected str, got {type(v).__name__} ({v!r})"
            )
        out.add(v)
    return frozenset(out)
```

### `engine/qa/sandbox.py._hardened_env` (refactor)

```python
from engine._sandbox.env import build_safe_env

def _hardened_env(
    guard_dir: Path,
    *,
    extras: Iterable[str] = (),
) -> dict[str, str]:
    """Constrói env safe + sitecustomize.py preload + marker.

    Refactor (QA-11): delega base pra build_safe_env(extras=...);
    adiciona PYTHONPATH guard e FORGE_QA_SANDBOX=1 por cima.
    """
    env = build_safe_env(extras=extras)
    existing = env.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = f"{guard_dir}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = str(guard_dir)
    env["FORGE_QA_SANDBOX"] = "1"
    return env
```

### `engine/qa/__init__.py._alert_sensitive_drops` (novo)

```python
from engine._sandbox.env import inspect_dropped, is_sensitive
from engine.ui.three_paths import mentor_calm_three_paths

def _alert_sensitive_drops(card_extras: Iterable[str]) -> None:
    """Pré Phase 3: alerta se vars sensitive serão dropadas.

    Dispara mentor_calm_three_paths com 3 paths:
      1) ignore → segue com env reduzido (perda de funcionalidade aceita)
      2) declare no card → user vai editar card e re-rodar
      3) grant no projeto → user roda forge reconfigure e adiciona em
         workflow-config.qa.sensitive-env-grants
    """
    dropped = inspect_dropped(extras=card_extras)
    sensitive = [v for v in dropped if is_sensitive(v)]
    if not sensitive:
        return
    mentor_calm_three_paths(
        title="Variáveis sensitive serão dropadas no sandbox",
        what_failed=f"Detectadas {len(sensitive)} vars sensitive no env do pai não declaradas por card: {', '.join(sensitive)}",
        where="engine/qa Phase 3 sandbox boot",
        why_matters=[
            "subprocess de validators rodará sem essas vars",
            "se validator/card depende delas, vai falhar com erro de auth/config",
            "se NÃO depende, o drop é a defesa funcionando (zero ação)",
        ],
        paths=[
            ("Ignorar e seguir", "validator/card não depende dessas vars — drop esperado"),
            ("Declarar no card", "editar qa-extensions.env-needs do card relevante e re-rodar"),
            ("Grant no projeto", "rodar `forge reconfigure` e adicionar em qa.sensitive-env-grants"),
        ],
    )
```

### `engine/verify.py:624` (patch mínimo)

```python
from engine._sandbox.env import build_safe_env

# ... linha 624:
proc = subprocess.run(
    [sys.executable, str(spec.script_path), "--project-root", str(project_root)],
    check=False,
    capture_output=True,
    text=True,
    timeout=60,
    env=build_safe_env(),     # NEW: env reduzido (QA-11)
)
```

### `engine/cards/loader.py` (extensão)

```python
@dataclass(frozen=True)
class Card:
    # ... campos existentes
    env_needs: tuple[str, ...] = ()
    sensitive_env_needs: tuple[str, ...] = ()


def load_card(yaml_path: Path) -> Card:
    raw = _load_yaml(yaml_path)
    ext = raw.get("qa-extensions", {}) or {}
    env_needs = tuple(ext.get("env-needs", []) or [])
    sensitive_env_needs = tuple(v for v in env_needs if is_sensitive(v))
    return Card(
        # ... campos existentes
        env_needs=env_needs,
        sensitive_env_needs=sensitive_env_needs,
    )
```

### `engine/cards/grant.py` (novo)

```python
"""Decisão sensitive-var grant pra cards em init/reconfigure."""

from dataclasses import dataclass
from typing import Iterable

from engine.cards.loader import Card


@dataclass(frozen=True)
class GrantDecision:
    """Resultado de evaluate_sensitive_grants."""
    granted: tuple[str, ...]          # vars aprovadas no prompt
    denied_cards: tuple[str, ...]     # nomes de cards desativados
    new_grants_to_persist: tuple[str, ...]  # delta pra workflow-config


def evaluate_sensitive_grants(
    cards_to_activate: Iterable[Card],
    workflow_config: WorkflowConfig,
) -> GrantDecision:
    """Per card, per sensitive var não-granted, dispara prompt 3-caminhos.

    Returns
    -------
    GrantDecision
        Resumo do que foi granted, denied, e o delta a persistir em
        workflow_config.qa.sensitive_env_grants.

    Raises
    ------
    UserAbortError
        Se user escolher path 3 (abort) em qualquer prompt.
    """
    # implementação detalhada no plan de execução
    ...
```

### `validators/validate_qa_extensions.py` (extensão)

Adicionar schema check pra campo `env-needs`:

- Tipo: `list[str]`, non-empty se presente
- Cada elemento: string non-empty, sem whitespace interno
- **NÃO rejeita** pattern sensitive em load-time — decisão é runtime
  (init/reconfigure dispara grant), não compile-time

### `docs/schemas/qa-extensions.md` (extensão)

Adicionar seção `env-needs (opcional)` com exemplo:

```yaml
qa-extensions:
  env-needs:
    - GITHUB_TOKEN      # bate pattern sensitive → exige grant
    - JAVA_HOME         # non-sensitive → passa direto
```

### `docs/schemas/workflow-config.md` (extensão)

Adicionar seção `qa.sensitive-env-grants (opcional)`:

```yaml
qa:
  sensitive-env-grants:
    - GITHUB_TOKEN      # granted em init/reconfigure pelo user
```

## §7. Error handling + edge cases

### 7.1 Erros explícitos (raise)

| Erro | Onde | Quando |
|---|---|---|
| `TypeError` | `build_safe_env._validate_extras` | `extras` contém elemento não-string |
| `QAExtensionsValidationError` | `validators/validate_qa_extensions.py` | `env-needs` malformado (não-list, item non-string, item vazio, whitespace interno) |
| warning fail-safe | `engine.cards.grant.evaluate_sensitive_grants` | `workflow_config.qa.sensitive_env_grants` corrupto (não-list) → trata como `[]`, warning visível |
| `UserAbortError` | `engine.cards.grant.evaluate_sensitive_grants` | user escolhe path 3 (abort) em grant prompt |
| `KeyError` (em validator buggy) | subprocess do validator | validator canon tenta `os.environ[var]` pra var não-allowed → reportado como `qa-finding status:error` (não swallow) |

### 7.2 Erros silenciosos (intencionais)

- `extras` contém var ausente em `os.environ` → filter natural, sem
  log (subprocess naturalmente não vê var inexistente; alertar viraria
  ruído).
- Grant prévio em workflow-config inclui var que não bate `is_sensitive`
  hoje → mantém grant (user pode ter editado manual ou regex evoluiu;
  remover silenciosamente quebraria contrato).
- Card declara `env-needs: []` → no-op, sem prompt, sem extras.
- Card declara `env-needs` com var já em `CORE_ALLOWLIST` → no-op
  redundante (set union dedupica).

### 7.3 Edge cases

1. **Card desativado tinha grant aprovado.** Grant permanece em
   `workflow-config.qa.sensitive-env-grants`. Revoke explícito só via
   reconfigure manual; NÃO implementado v1 (gap opt-in
   `forge reconfigure --revoke-grants`).
2. **Multiple cards declaram mesma sensitive var.** Union, prompt único
   pro user — não pergunta uma vez por card.
3. **Card declara var custom non-sensitive** (ex.: `MY_CUSTOM_VAR`).
   Passa direto, sem prompt. Risco mínimo: user instalou o card (trust
   chain), var não bate pattern.
4. **Race entre `inspect_dropped()` e `build_safe_env()`.** Snapshot no
   início de `phase_3_sandbox`, caller responsabiliza ordem das
   chamadas (alert primeiro, build depois). Não tentamos lock.
5. **Subprocess que faz `os.environ.update(...)` internamente.** Fora
   de nosso controle, não tentamos guard. Card extension pode set vars
   no próprio subprocess; isso afeta só o próprio subprocess.
6. **Validator legítimo lê `os.environ['MEU_PROJETO_CONFIG']`.** Card
   declara `env-needs: [MEU_PROJETO_CONFIG]`. Var non-sensitive, passa
   sem prompt, validator vê normalmente.
7. **`forge qa` em CI sem sensitive vars no env.** `inspect_dropped`
   não retorna sensitive (env do CI já é mínimo), sem alert, fluxo
   limpo.
8. **`forge qa` em laptop dev com `AWS_*` exportado.** Alert dispara,
   user vê 3-caminhos, escolhe — comportamento desejado.

### 7.4 Migração / backward-compat

- **Cards existentes sem `env-needs`** → campo opcional, default
  `()`, zero impacto.
- **Workflow-configs existentes sem `qa.sensitive-env-grants`** →
  opcional, default `[]`, zero impacto.
- **`forge verify` pré-fix vs pós-fix** → env do subprocess fica MAIS
  estrito. Risco baixo (grep validators/ vazio prova que canon não
  consome env). Validação via pytest no PR — se algum validator quebrar,
  fix é adicionar a var em `CORE_ALLOWLIST` (decisão explícita) ou
  declarar como `env-needs` num card relevante.

## §8. Testing strategy

### 8.1 Unit `tests/engine/_sandbox/test_env.py` (novo) — 12 tests

| # | Test | Foco |
|---|---|---|
| 1 | `test_build_safe_env_returns_core_allowlist_intersection` | dict só com vars em CORE_ALLOWLIST ∩ os.environ |
| 2 | `test_build_safe_env_drops_arbitrary_var` | vars fora do allowlist são excluídas |
| 3 | `test_build_safe_env_drops_sensitive_pattern_match` | `AWS_TOKEN`, `*_SECRET`, etc. dropados |
| 4 | `test_build_safe_env_includes_extras` | extras válidos adicionados ao env |
| 5 | `test_build_safe_env_extras_filtered_if_not_in_environ` | extras ausentes em os.environ silenciosamente filtrados |
| 6 | `test_build_safe_env_raises_typeerror_on_non_string_extras` | `extras=[1]` → TypeError |
| 7 | `test_build_safe_env_empty_extras_default` | chamada sem `extras` retorna só CORE ∩ environ |
| 8 | `test_inspect_dropped_returns_sorted_list` | output determinístico |
| 9 | `test_inspect_dropped_respects_extras` | vars em extras não aparecem como dropped |
| 10 | `test_is_sensitive_matches_token_patterns` | TOKEN, SECRET, PASSWORD, AUTH, CREDENTIAL, API_KEY, PRIVATE_KEY |
| 11 | `test_is_sensitive_case_insensitive` | `Github_Token`, `aws_secret_access_key` bate |
| 12 | `test_is_sensitive_negative_cases` | `JAVA_HOME`, `PATH`, `MY_VAR` não bate |

### 8.2 Unit `tests/validators/test_validate_qa_extensions.py` (extensão) — 5 tests

| # | Test |
|---|---|
| 1 | `test_env_needs_optional_absent_ok` |
| 2 | `test_env_needs_list_of_strings_ok` |
| 3 | `test_env_needs_non_list_raises` |
| 4 | `test_env_needs_non_string_item_raises` |
| 5 | `test_env_needs_empty_string_item_raises` |

### 8.3 Unit `tests/engine/cards/test_loader_env_needs.py` (novo/extensão) — 3 tests

| # | Test |
|---|---|
| 1 | `test_load_card_parses_env_needs_into_tuple` |
| 2 | `test_load_card_classifies_sensitive_env_needs` |
| 3 | `test_load_card_no_env_needs_defaults_empty` |

### 8.4 Unit `tests/engine/cards/test_grant.py` (novo) — 7 tests, UI mockada via fixture

| # | Test |
|---|---|
| 1 | `test_no_sensitive_needs_skips_prompt` |
| 2 | `test_already_granted_skips_prompt` |
| 3 | `test_grant_path_adds_to_workflow_config` |
| 4 | `test_deny_path_deactivates_card` |
| 5 | `test_abort_path_raises_user_abort` |
| 6 | `test_multiple_cards_same_var_single_prompt` |
| 7 | `test_grant_persistence_idempotent` |

### 8.5 Refactor `tests/engine/qa/test_sandbox.py` (existente) — 4 tests novos

| # | Test |
|---|---|
| 1 | `test_hardened_env_delegates_to_build_safe_env` |
| 2 | `test_hardened_env_preserves_pythonpath_guard_prepend` |
| 3 | `test_hardened_env_preserves_forge_qa_sandbox_marker` |
| 4 | `test_hardened_env_propagates_extras_to_build_safe_env` |

### 8.6 Refactor `tests/engine/test_verify.py` (existente)

Validar que tests existentes continuam passando após patch da linha
624. Sem novos tests dedicados a env (cobertura já em §8.1); validar
suite verify completa.

### 8.7 Integration `tests/integration/test_qa_env_hardening.py` (novo, marker `integration`) — 4 tests E2E

| # | Test |
|---|---|
| 1 | `test_secret_in_parent_env_does_not_leak_to_subprocess` (set env var sensitive, roda `run_qa`, lê stderr/findings, assert ausência) |
| 2 | `test_card_env_needs_chain_grant_to_subprocess` (card declara non-sensitive, run, assert var visível no subprocess fixture) |
| 3 | `test_alert_fires_when_sensitive_unwhitelisted_present` (env tem AWS_TOKEN, nenhum card declara, run, assert mentor_calm output triggered) |
| 4 | `test_alert_silent_when_no_sensitive_present` (env mínimo, run, assert alert NÃO disparado) |

### 8.8 Integration `tests/integration/test_card_grant_flow.py` (novo) — 4 tests

| # | Test |
|---|---|
| 1 | `test_first_activation_prompts_and_persists_grant` |
| 2 | `test_second_activation_same_var_no_prompt` (idempotência) |
| 3 | `test_deny_path_disables_card_in_workflow_config` |
| 4 | `test_manual_revoke_via_reconfigure_removes_grant` |

### 8.9 E2E extensão de `tests/e2e/test_qa_cli_smoke.py` — 1 test (marker `e2e`)

| # | Test |
|---|---|
| 1 | `test_forge_qa_cli_no_secret_leak_smoke` (export AWS_TOKEN, run `forge qa`, parse QA-REPORT.json, grep findings stderr, assert vazio) |

**Test count delta:** +40 tests projetado. Baseline atual pós-round =
877 tests → projeção pós-implementação: ~917 tests.

**Property test deferido:** uso de `hypothesis` pra fuzz de
`build_safe_env` contra inputs arbitrários seria útil mas
`hypothesis` não está no projeto hoje; over-eng pra v1. Gap opt-in
`QA-11-prop-test` se útil aparecer.

## §9. Scope decisions (out-of-scope explícito v1)

- **Subprocess wrapper de alto nível** (`run_isolated(...)`) — rejeitado
  em brainstorm shape Q (esconde subprocess, kwargs proxying brittle,
  perde a clareza de `subprocess.run(env=build_safe_env())`).
- **Context manager** `with safe_env():` — rejeitado; não-pythonic pra
  subprocess (env de subprocess se passa por kwarg, não por scope), e
  abriria race condition em async/threads.
- **Property-based test** (hypothesis) — deferred (dep nova no
  projeto, over-eng pra v1, gap opt-in se útil).
- **Per-card grant** (vs per-projeto) — deferred (KISS; user prefere
  broad grant 1x, não micro-permissão).
- **Alert no `forge verify`** — deferido (verify não roda untrusted
  code hoje, alert vira ruído; revisitar quando cards extension
  entrarem em verify cascade).
- **Explicit grant revoke command** (`forge reconfigure
  --revoke-grants`) — não implementado v1, gap opt-in se necessidade
  aparecer em uso real.
- **Per-fixture env** (todas fixtures de um run compartilham env do
  sandbox) — YAGNI; nenhum caso de uso observado.

## §10. Doc-sync impacto

Lista do que precisa atualizar quando a implementação shippar (NÃO
nesta task — só anotação pro plan futuro):

- `CHANGELOG.md` `### Added` — `build_safe_env` helper, campo
  `env-needs` em qa-extensions, campo `sensitive-env-grants` em
  workflow-config; `### Changed` — `engine.verify` agora usa env
  reduzido pra subprocess de validators.
- `docs/design/08-session-handoff.md` — "Última atualização" + stats
  test count.
- `docs/design/04-pending.md` — fechar Gap QA-11 com `✅ resolvido
  2026-06-08` (formato padrão).
- `docs/schemas/qa-extensions.md` — seção `env-needs`.
- `docs/schemas/workflow-config.md` — seção `qa.sensitive-env-grants`.
- `.claude/rules/testing.md` — atualizar baseline test count (877 →
  ~917).
- `README.md` se stats mudarem materialmente (test count, validator
  count, schema count).

## §11. References

- **Gap origem:** `docs/design/04-pending.md` linhas 1933-1953
  (Gap QA-11 — Sandbox env hardening: allowlist vs blocklist).
- **Spec base:** `docs/superpowers/specs/2026-06-05-forge-qa-design.md`
  (`forge qa` design — contém §17 IN-02 onde QA-11 foi surfaced
  inicialmente).
- **Decisões relacionadas:** Decisão 22 (zero runtime deps em outras
  skills), Decisão 30 (sandbox isolation — CWD do subprocess validator
  = `.planning/qa/<run_id>/fixtures/`), QA-6 (rejected — custom rubric
  per project; mesma razão pela qual override irrestrito de env via
  workflow-config simples é rejeitado aqui).
- **Brainstorm session:** `superpowers:brainstorming`, 2026-06-08, 5
  perguntas chave (threat model, config surface, observability, scope,
  sensitive grant) + 1 pergunta shape (pure dict builder vs
  wrapper/context manager — pure dict builder venceu).
- **Código a refatorar:** `engine/qa/sandbox.py:154-162`
  (`_hardened_env`), `engine/verify.py:624` (subprocess sem `env=`).
