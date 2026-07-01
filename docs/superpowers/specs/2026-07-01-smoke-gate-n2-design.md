# Smoke Gate (Tema 6 Nível 2) — Design de Implementação

> **Status:** spec de implementação. Concretiza o **Caminho A** do Nível 2
> (smoke) da spec de produto `2026-06-30-runtime-visual-verification-design.md`.
> Voz: mentor calmo.
> **Decisão de produto (travada):** Caminho A — o consumidor DECLARA o comando de
> smoke; o forge só o RODA. Encaixe: STEP do `forge verify`. N3 (screenshot)
> segue deferido pós-piloto.

---

## 1. O que este nível fecha

O piloto MeoBonsai expôs que o forge verifica artefato estático mas nunca "o app
sobe" — o "isso roda?" ficava fora do loop (spec de produto §1). O Nível 1
(build-only, Fase 1) fechou "compila?". Este nível fecha "**sobe e passa 1 assert
mínimo?**" — um degrau acima de compilar, sem virar suíte de testes nem CI.

**Caminho A (por que):** "o 1 assert" e a toolchain de execução (runner, device)
são específicos do consumidor. A spec de produto §3 põe como non-goal "não escolher
o assert" e "não substituir a suíte". Logo o forge NÃO adivinha o smoke — o
consumidor declara o comando; o forge é runner fino. Adivinhar reintroduziria o
"teste frágil ou inerte" que o piloto mandou evitar.

---

## 2. Reuso da fronteira de execução externa (Fase 1)

Zero infra nova. O smoke é MAIS UM consumidor da fronteira `engine/external_exec.py`
(Decisão 33) e do padrão de `engine/verify.py::_run_native_gates`:

- `resolve_invocation(candidates, project_root)` → skip-se-ausente (`None`).
- `run_external_tool(argv, project_root, timeout)` → classifica (pass/fail/degraded), env reduzido, check=False, sem auto-fix.
- `_map_external_result(res, gate_name, fail_on_violation)` → `_ValidatorResult`.
- `_skipped_gate_result(gate_name, message)` → skip com mensagem mentor-calmo.
- Helpers de config já genéricos: `_gate_enabled` / `_gate_timeout` / `_gate_fail_on_violation` / `_gate_cfg` / `_native_gate_block`.

Implementação = uma função nova `_run_smoke_gate(config, project_root)` mesclada em
`_run_native_gates`, espelhando `_run_build_gates`.

---

## 3. Config — `native-gates.smoke`

```yaml
native-gates:
  smoke:
    enabled: true          # OPT-IN: default False (entra em _OPT_IN_GATES)
    cmd: ["./gradlew", "testDebugUnitTest"]   # o consumidor DECLARA; único (não per-plataforma)
    timeout: 600           # default 600 (smoke pode ser lento)
    fail-on-violation: false  # default False (informativo; warn não reprova)
```

- **`enabled` opt-in (default False):** smoke pode pedir device/ser lento →
  explícito. `_OPT_IN_GATES` passa a `{"build", "smoke"}`.
- **`cmd` único (não per-plataforma):** YAGNI. O consumidor declara um smoke. Se um
  consumidor multiplataforma real precisar de per-plataforma, é extensão futura
  (registrar em pending, não especular agora).
- **`timeout` default 600**, **`fail-on-violation` default False** (informativo,
  consistente com o build gate — não surpreende automação que assume verify
  read-ish; consumidor opta por reprovar).

---

## 4. Semântica (mapeamento LOCKED, reusa `_map_external_result`)

- `cmd` ausente/não-configurado → `skipped` (mensagem mentor-calmo: como declarar `native-gates.smoke.cmd`).
- `cmd` presente mas toolchain/binário não resolve (`resolve_invocation` → None) → `skipped` (mensagem: instale a toolchain).
- roda + exit 0 → `pass` (coverage `substantive`).
- roda + exit ≠ 0 → `warn` (ou `fail` se `fail-on-violation: true`).
- **timeout / OSError (device ausente, hang) → `degraded`, NUNCA `fail`** (Disciplina 9: dependência externa ausente não reprova a feature; o `run_external_tool` já devolve `degraded` nesses casos).

Guard de stack: diferente do ktlint (que tem `_ktlint_applies`), o smoke é
governado pela PRESENÇA de `cmd` no config — se o consumidor não declarou, não roda.
Sem heurística de stack própria.

---

## 5. Non-goals

- **Não** gerar/injetar teste no consumidor (é dono da suíte).
- **Não** gerenciar/subir emulador ou device — o `cmd` do consumidor é dono disso; device ausente → `degraded`.
- **Não** escolher o assert-âncora — o consumidor escolhe no `cmd`.
- **Não** rodar per-plataforma no primeiro nível (YAGNI; extensão futura).
- **Não** N3 (screenshot) — deferido pós-piloto.

---

## 6. Sinergia — fecha o follow-on I-02

O smoke é o **3º gate nativo** (ktlint, build, smoke). O follow-on **I-02**
(`04-pending`) previa: quando o 3º gate chegar, extrair o helper de teste
duplicado `_write_fake_gradlew`/`_fake_run` (hoje em `test_verify_build_only.py` e
`test_verify_native_gates.py`) pra um módulo compartilhado
(`tests/engine/helpers/external_exec.py` ou `conftest.py`). Esta impl fecha o I-02:
os testes do smoke consomem o helper compartilhado, e os dois módulos existentes
migram pra ele.

---

## 7. Testes (TDD)

`tests/engine/test_verify_smoke_gate.py`, reusando o helper compartilhado (I-02):

- smoke `enabled: false` (default) → gate não roda (`[]`).
- `enabled: true` sem `cmd` → `skipped` (mensagem de como declarar).
- `cmd` declarado + fake runner exit 0 → `pass` (substantive).
- `cmd` declarado + fake runner exit ≠ 0 → `warn`.
- `cmd` + exit ≠ 0 + `fail-on-violation: true` → `fail`.
- `cmd` + toolchain ausente (resolve None) → `skipped`.
- `cmd` + timeout → `degraded`.
- guard greenfield: config vazio → `_run_native_gates` devolve `[]` (não roda smoke).

---

## 8. Escopo de arquivos

- `engine/verify.py` — `_run_smoke_gate` + wire em `_run_native_gates` + `smoke` em `_OPT_IN_GATES`.
- `tests/engine/test_verify_smoke_gate.py` — novo.
- `tests/engine/helpers/` (ou conftest) — helper compartilhado extraído (I-02).
- `tests/engine/test_verify_build_only.py` + `test_verify_native_gates.py` — migram pro helper.
- `CHANGELOG.md`, `docs/design/04-pending.md` (fecha I-02 + registra smoke), guia de `native-gates` (se existir).

---

## 9. Critério de "pronto" / veredito

- `.venv/bin/pytest` full lane verde; TDD (teste falha antes, passa depois).
- plan-auditor 2 rodadas; review zero-tolerância; verify continua read-ish por default (smoke opt-in default off).
- **Veredito real:** re-piloto MeoBonsai — declarar `native-gates.smoke.cmd` num consumer real e ver "isso roda?" entrar no loop sem ruído. N3 só se o piloto justificar.

## Cross-refs

- Spec de produto (Caminho A/B/C, níveis): `docs/superpowers/specs/2026-06-30-runtime-visual-verification-design.md`.
- Fronteira reusada: `engine/external_exec.py`, `engine/verify.py::_run_native_gates` (Fase 1, Decisão 33).
- I-02: `docs/design/04-pending.md` §Follow-on.
