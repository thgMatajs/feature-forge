<!--
Fragment injetado pelo card `skie-bridge` no `task-contract-writer`.
Extension point: after:Allowed Files
-->

### Card `skie-bridge` — allowed-files e validações iOS

Tarefas que tocam código iOS consumindo APIs do shared via SKIE devem
declarar allowed-files e validation steps específicos.

**Allowed-files canônicos (iOS Swift)**

```yaml
allowed_files:
  - "iosApp/iosApp/Features/{Feature}/**/*.swift"
  - "iosApp/iosApp/Shared/**/*.swift"           # opcional, somente se a tarefa toca platform shims
  - "shared/src/iosMain/kotlin/**/*.kt"         # opcional, somente se a tarefa adiciona iosMain actuals
```

Exclusões implícitas (não precisam ser listadas):

- `iosApp/iosApp.xcodeproj/**` (gerado/managed pelo Xcode)
- `iosApp/Pods/**` (este projeto é CocoaPods-free; pasta não existe)
- `**/build/**`, `**/.gradle/**`

**NÃO** liste `iosApp/scripts/build-shared-framework.sh` como allowed
salvo se a tarefa for explicitamente sobre o pipeline de build do
framework.

**Validation steps canônicos**

Adicione ao bloco `validations` da task:

```yaml
validations:
  - name: "build shared framework iOS"
    command: "./gradlew :shared:linkPodReleaseFrameworkIosArm64"
    rationale: "Garante que SKIE gera o framework sem erro de bridge."

  - name: "smoke test simulador iOS"
    command: "./scripts/run-ios-simulator.sh"
    rationale: "Build + run no simulador valida a bridge end-to-end."

  - name: "swift style"
    command: "./scripts/swift-style.sh --lint"
    rationale: "SwiftLint + SwiftFormat estritos em código Swift novo."

  - name: "bridge sanity"
    command: "python3 .claude/cards/skie-bridge/validators/check-no-manual-async-wrappers.py"
    rationale: "Detecta wrappers manuais de async (warn, não bloqueante)."
```

**Quando NÃO incluir**

Tarefas que tocam apenas `commonMain` sem expor nova API ao iOS não
precisam desses validators — basta o build do shared. Tarefas que
adicionam `expect/actual` mas não tocam SwiftUI também ficam só com o
build do shared (não há código Swift novo para lint).

**Anti-padrões a flaggar no contract**

- Allowed-files com pattern `iosApp/**` puro (amplo demais) — restrinja
  por feature.
- `Pods/`, `*.xcodeproj/`, `DerivedData/` em allowed-files — esses são
  artefatos gerenciados.
- Falta de `swift-style.sh --lint` no validations quando há `.swift` no
  diff.
