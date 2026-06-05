"""Parser tests for `check_secrets` validator (R1.1 Task 2).

Cobre os 2 parsers JSON que normalizam output das tools nativas
(gitleaks + trufflehog) em ``SecretFinding`` — o shape comum consumido
por ``apply_overrides`` (Task 4) e pelo render 3-caminhos (Task 4).

Contratos enforced:

- ``_parse_gitleaks_json``
    - input JSON array → list[SecretFinding] (verified sempre False).
    - empty string / non-list root / JSON inválido → [].
    - entry sem campo opcional → graceful (defaults sensatos).
    - snippet truncado em 80 chars.

- ``_parse_trufflehog_json``
    - input NDJSON (1 finding por linha) → list[SecretFinding] com
      verified honesto vindo do field ``Verified``.
    - linha vazia / malformada → skip silencioso.
    - entry sem ``SourceMetadata`` → file="", line=0 sem crash.
    - snippet truncado em 80 chars.

Spec: docs/superpowers/specs/2026-06-05-check-secrets-design.md §2 + §3
Plan: docs/superpowers/plans/2026-06-05-check-secrets-implementation.md
"""

from __future__ import annotations

from pathlib import Path

import check_secrets as v


_FIXTURES = Path(__file__).parent.parent / "fixtures" / "secrets"


# ── _parse_gitleaks_json ────────────────────────────────────────────────────


def test_parse_gitleaks_happy_path_returns_two_findings() -> None:
    raw = (_FIXTURES / "gitleaks_output_sample.json").read_text()
    findings = v._parse_gitleaks_json(raw)
    assert len(findings) == 2

    aws, fb = findings
    assert aws.file == "app/auth/AuthRepository.kt"
    assert aws.line == 42
    assert aws.kind == "aws-access-key"
    assert aws.snippet == "AKIAIOSFODNN7EXAMPLE"
    assert aws.verified is False  # gitleaks NUNCA verifica

    assert fb.file == "src/config/firebase.ts"
    assert fb.line == 15
    assert fb.kind == "firebase-token"
    assert fb.snippet.startswith("1//0abcd")
    assert fb.verified is False


def test_parse_gitleaks_empty_string_returns_empty_list() -> None:
    assert v._parse_gitleaks_json("") == []


def test_parse_gitleaks_invalid_json_returns_empty_list() -> None:
    assert v._parse_gitleaks_json("not json {") == []


def test_parse_gitleaks_non_list_root_returns_empty_list() -> None:
    assert v._parse_gitleaks_json('{"oops": 1}') == []


def test_parse_gitleaks_entry_missing_fields_graceful() -> None:
    """Entry sem campos obrigatórios não levanta — defaults sensatos."""
    raw = '[{"RuleID": "x"}]'
    findings = v._parse_gitleaks_json(raw)
    assert len(findings) == 1
    f = findings[0]
    assert f.file == ""
    assert f.line == 0
    assert f.kind == "x"
    assert f.snippet == ""
    assert f.verified is False


def test_parse_gitleaks_snippet_truncated_to_80_chars() -> None:
    long_secret = "A" * 200
    raw = (
        '[{"RuleID": "aws", "File": "f.kt", "StartLine": 1, '
        f'"Secret": "{long_secret}"}}]'
    )
    findings = v._parse_gitleaks_json(raw)
    assert len(findings) == 1
    assert len(findings[0].snippet) == 80


# ── _parse_trufflehog_json ──────────────────────────────────────────────────


def test_parse_trufflehog_happy_path_returns_two_findings() -> None:
    raw = (_FIXTURES / "trufflehog_output_sample.json").read_text()
    findings = v._parse_trufflehog_json(raw)
    assert len(findings) == 2

    aws, fb = findings
    assert aws.file == "app/auth/AuthRepository.kt"
    assert aws.line == 42
    assert aws.kind == "AWS"
    assert aws.snippet == "AKIAIOSFODNN7EXAMPLE"
    assert aws.verified is True  # fixture marca Verified=true

    assert fb.file == "src/config/firebase.ts"
    assert fb.line == 15
    assert fb.kind == "Firebase"
    assert fb.snippet.startswith("1//0abcd")
    assert fb.verified is False  # fixture marca Verified=false


def test_parse_trufflehog_empty_lines_ignored() -> None:
    raw = (
        '\n\n'
        '{"DetectorName":"AWS","Verified":true,"Raw":"x",'
        '"SourceMetadata":{"Data":{"Filesystem":{"file":"a.kt","line":1}}}}\n'
        '\n'
    )
    findings = v._parse_trufflehog_json(raw)
    assert len(findings) == 1
    assert findings[0].kind == "AWS"


def test_parse_trufflehog_malformed_line_skipped() -> None:
    """Linha malformada não interrompe parsing — continua com as válidas."""
    valid = (
        '{"DetectorName":"AWS","Verified":true,"Raw":"x",'
        '"SourceMetadata":{"Data":{"Filesystem":{"file":"a.kt","line":1}}}}'
    )
    other = (
        '{"DetectorName":"GCP","Verified":false,"Raw":"y",'
        '"SourceMetadata":{"Data":{"Filesystem":{"file":"b.ts","line":2}}}}'
    )
    raw = f"{valid}\n{{broken json\n{other}"
    findings = v._parse_trufflehog_json(raw)
    assert len(findings) == 2
    assert findings[0].kind == "AWS"
    assert findings[1].kind == "GCP"


def test_parse_trufflehog_missing_metadata_graceful() -> None:
    """Entry sem SourceMetadata → file="" line=0 sem crash."""
    raw = '{"DetectorName":"AWS","Verified":true,"Raw":"x"}'
    findings = v._parse_trufflehog_json(raw)
    assert len(findings) == 1
    f = findings[0]
    assert f.file == ""
    assert f.line == 0
    assert f.kind == "AWS"
    assert f.verified is True


def test_parse_trufflehog_snippet_truncated_to_80_chars() -> None:
    long_secret = "B" * 200
    raw = (
        f'{{"DetectorName":"AWS","Verified":true,"Raw":"{long_secret}",'
        '"SourceMetadata":{"Data":{"Filesystem":{"file":"f.kt","line":1}}}}'
    )
    findings = v._parse_trufflehog_json(raw)
    assert len(findings) == 1
    assert len(findings[0].snippet) == 80


def test_parse_trufflehog_empty_string_returns_empty_list() -> None:
    assert v._parse_trufflehog_json("") == []
