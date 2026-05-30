#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# Validator: check-room-migrations
# Card:      room-database v1.0.0
# Runs-on:   [verify-task]
# Severity:  error
#
# Objetivo:
#   Falhar quando o schema de uma @Entity mudou (campo novo/removido/
#   renomeado, tipo alterado, índice modificado) SEM uma migration
#   correspondente declarada — seja via @AutoMigration na @Database, seja
#   via Migration manual registrada em db/migrations/ + addMigrations().
#
# Heurística pretendida (Phase 5):
#   1. Encontrar todas as @Entity declaradas em commonMain (data/local/entity/).
#   2. Para cada Entity, comparar o snapshot atual de campos+índices+
#      primaryKey contra o último schema exportado em schemas/<DB>/<version>.json
#      (gerado pelo Room com `exportSchema = true`).
#   3. Para cada divergência detectada:
#       a. Confirmar que @Database.version foi incrementado.
#       b. Confirmar que existe @AutoMigration(from=N-1, to=N) ou que
#          db/migrations/<Feature>MigrationN-1toN.kt foi adicionado E
#          registrado via .addMigrations(...) no builder.
#       c. Confirmar que o YAML data-contract-spec.yaml em
#          `room-tables[*].migrations.history` lista a transição com
#          `change` descritivo.
#   4. Falhar com mensagem apontando exatamente Entity + campo + arquivo
#      esperado de migration.
#
# Sinais a usar:
#   - AST: ler @Entity classes via tree-sitter Kotlin (ou regex pragmática
#     se AST não estiver disponível) e extrair fields + @ColumnInfo +
#     @PrimaryKey + @Index.
#   - Snapshots: ler `schemas/<package>/<DB_NAME>/<version>.json` (Room
#     export) — fonte mais confiável que parse de Kotlin.
#   - data-contract-spec.yaml: ler `room-tables[*].schema.columns` +
#     `migrations.history` da feature em curso.
#
# Saída (CLI):
#   - exit 0  → todas as Entities têm migration coerente ou nenhuma mudança.
#   - exit 1  → ao menos uma divergência sem migration. Mensagem listando:
#         feature/.../BonsaiEntity.kt
#         + Detectado: campo `updated_at` (INTEGER nullable) novo
#         - Esperado: @AutoMigration(from=1, to=2) na BonsaiDataBase
#                     OU db/migrations/BonsaiMigration1to2.kt
#         - Esperado em data-contract-spec.yaml:
#             room-tables[bonsai].migrations.history[from=1,to=2]
#
# TODO Phase 5:
#   - Implementar parser Kotlin (regex pragmática suficiente para v1).
#   - Implementar diff de schemas/ JSON antes/depois.
#   - Implementar cross-check com data-contract-spec.yaml.
#   - Cobrir corner cases: rename via @ColumnInfo(name=...), Type
#     converters via @TypeConverter (mudança quebra schema), composite
#     primaryKey, foreignKeys.
#   - Mensagens em pt-BR alinhadas com tom do tech-spec.
# ──────────────────────────────────────────────────────────────────────────

import sys


def main() -> int:
    # TODO Phase 5: implementar parser + diff + cross-check + report.
    sys.stdout.write(
        "check-room-migrations: stub (Phase 5 pending). "
        "Sem verificação ativa neste momento — placeholder retorna sucesso.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
