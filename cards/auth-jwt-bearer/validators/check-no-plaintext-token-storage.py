#!/usr/bin/env python3
"""
check-no-plaintext-token-storage.py — STUB (Phase 5 placeholder)

Validator do card auth-jwt-bearer.

Falha quando código de auth salva refresh-token ou access-token em storage
não seguro (SharedPreferences plain, UserDefaults plain, localStorage,
arquivo texto). Storage canônico é encrypted DataStore (Android Tink),
Android Keystore, iOS Keychain ou cookie HttpOnly Secure (Web).

Regras base:

  - Android: edit() / putString() de SharedPreferences com chave que case
             ^(refresh_token|access_token|jwt|bearer).* → fail.
             Permitido apenas EncryptedSharedPreferences / EncryptedDataStore.

  - iOS:     UserDefaults.standard.set(...) onde valor refere
             refreshToken / accessToken / jwt → fail.
             Permitido apenas Keychain Services.

  - Web:     localStorage.setItem("refresh_token" | "access_token" | "jwt", ...) → fail.
             Permitido cookie HttpOnly Secure (setado pelo backend) ou
             sessionStorage apenas para access-token efêmero (warn, não fail).

  - Arquivo texto em disco com token: detectar via writeText / writeBytes
    em arquivos sob caminho auth/ → fail.

  - Permitidos: implementações cujo nome contenha "Encrypted", "Secure",
    "Keychain" ou "Keystore" no prefixo da classe.

Runs-on:   [pre-commit, verify-task]
Severity:  error
"""

from __future__ import annotations

import sys


# TODO Phase 5 — Implementação completa:
#   1. Resolver scope de arquivos via --paths (pre-commit passa file list).
#   2. Grep patterns por linguagem:
#        Kotlin/Android:
#          - SharedPreferences\.edit\(\).*put(String|Long)\(\s*"(refresh_token|access_token|jwt|bearer)
#          - context\.getSharedPreferences\(.*\)\.edit\(\) próximo a refresh|access|jwt
#          - Files\.write\(.*token.*\)
#        Swift/iOS:
#          - UserDefaults\.(standard|init).*\.set\(.*[rR]efresh[tT]oken
#          - UserDefaults\.(standard|init).*\.set\(.*[aA]ccess[tT]oken
#        TS/JS/Web:
#          - localStorage\.setItem\(\s*['"](refresh_token|access_token|jwt|bearer)
#   3. Allowlist:
#        - SecureTokenStorageAndroid.kt, SecureTokenStorageIOS.kt, SecureTokenStorageWeb.kt
#        - Classes cujo nome começa com Encrypted|Secure|Keychain|Keystore
#        - EncryptedDataStore, EncryptedSharedPreferences imports
#   4. Suportar --staged (pre-commit) e --branch <ref> (verify-task) modes.
#   5. Sair com:
#        0 — sem violações
#        1 — violações encontradas (printar arquivo:linha + sugestão de fix
#            apontando para Auth Strategy (JWT Bearer) > "Storage seguro do
#            refresh-token" do tech-spec)
#        2 — erro interno (config inválida, paths não encontrados)
#   6. Honrar workflow-config.yaml > conventions.auth.token-storage para
#      escolher quais implementações esperar (encrypted-datastore /
#      android-keystore / keychain / http-only-cookie).
#   7. Emitir JSON summary em --report-json para o forge agregar com
#      outros validators.


def main() -> int:
    print(
        "[auth-jwt-bearer] check-no-plaintext-token-storage.py — STUB Phase 5",
        file=sys.stderr,
    )
    print(
        "[auth-jwt-bearer] Implementação completa pendente. Retornando sucesso (no-op).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
