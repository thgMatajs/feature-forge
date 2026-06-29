"""Testes unit para `_check_mem` (Task 2, W-VENDOR Fase 1).

Dois testes centrais:
  - test_check_mem_fails_when_not_vendored: sem vendor → FAIL (não silencioso).
  - test_check_mem_health_warns_on_non_ok_check: H-001 — mem doctor retorna
    exit 0 mesmo com check não-ok no JSON; a saúde deve derivar do JSON, não
    do exit code.
"""
from pathlib import Path

from engine import doctor
from engine.integrations.mem import MemResult


def test_check_mem_fails_when_not_vendored(tmp_path):
    (tmp_path / ".git").mkdir()
    report = doctor._check_mem(tmp_path)            # -> _CategoryReport
    assert report.title == "mem"
    assert report.worst == doctor._STATUS_FAIL      # sem vendor → fail (não silencioso)
    assert any("vendor" in c.name for c in report.checks)


def test_check_mem_health_warns_on_non_ok_check(tmp_path, monkeypatch):
    # H-001: mem doctor retorna exit 0 mesmo com check não-ok; a saúde deve
    # derivar do JSON, não do exit code. Vendoriza um stub e injeta um doctor não-ok.
    binp = tmp_path / ".claude" / "bin" / "mem"
    binp.parent.mkdir(parents=True)
    binp.write_text("#!/bin/sh\nexit 0\n")
    binp.chmod(0o755)

    def fake_mem_call(project_root, args, **kw):
        # exit 0 (como o mem real), mas um check schema não-ok no JSON.
        return MemResult(
            found=True,
            exit_code=0,
            stdout='[{"check":"schema","status":"fail","detail":"db=3 code=4"}]',
            stderr="",
        )

    monkeypatch.setattr(doctor, "mem_call", fake_mem_call)
    report = doctor._check_mem(tmp_path)
    health = next(c for c in report.checks if c.name == "health")
    assert health.status == doctor._STATUS_WARN     # NÃO ok, apesar do exit 0


def test_check_mem_health_warns_on_dict_envelope(tmp_path, monkeypatch):
    """H-VENDOR-01: mem doctor retorna JSON não-lista (envelope de erro) → WARN.

    Antes da fix, iterar as chaves de um dict fazia bad=[] e health→OK (falso-OK).
    """
    binp = tmp_path / ".claude" / "bin" / "mem"
    binp.parent.mkdir(parents=True)
    binp.write_text("#!/bin/sh\nexit 0\n")
    binp.chmod(0o755)

    def fake_mem_call(project_root, args, **kw):
        # envelope de erro em vez de lista — o dict é válido JSON mas não-lista.
        return MemResult(
            found=True,
            exit_code=0,
            stdout='{"error":"db locked"}',
            stderr="",
        )

    monkeypatch.setattr(doctor, "mem_call", fake_mem_call)
    report = doctor._check_mem(tmp_path)
    health = next(c for c in report.checks if c.name == "health")
    assert health.status == doctor._STATUS_WARN     # NÃO ok — dict não é lista válida


def test_check_mem_health_warns_on_empty_list(tmp_path, monkeypatch):
    """H-VENDOR-02: mem doctor retorna lista vazia [] → WARN.

    Antes da fix, bad=[] com lista vazia fazia health→OK (falso-OK).
    A lista vazia indica que o mem não executou nenhum check (mem inicializado?).
    """
    binp = tmp_path / ".claude" / "bin" / "mem"
    binp.parent.mkdir(parents=True)
    binp.write_text("#!/bin/sh\nexit 0\n")
    binp.chmod(0o755)

    def fake_mem_call(project_root, args, **kw):
        return MemResult(
            found=True,
            exit_code=0,
            stdout="[]",
            stderr="",
        )

    monkeypatch.setattr(doctor, "mem_call", fake_mem_call)
    report = doctor._check_mem(tmp_path)
    health = next(c for c in report.checks if c.name == "health")
    assert health.status == doctor._STATUS_WARN     # NÃO ok — lista vazia ≠ saudável


def test_check_mem_pin_read_oserror_degrades_no_crash(tmp_path, monkeypatch):
    """P3 (cross-AI PR#32): OSError em pin/asset read NÃO crasha o doctor.

    `pin.read_text()`/`asset_v.read_text()` rodavam fora de try/except, logo
    após o guard `is_file()` — um EACCES ou delete-em-corrida (TOCTOU)
    propagava traceback cru de `forge doctor`, o comando que nunca deve
    crashar. A fix degrada pra um check WARN.
    """
    # Vendoriza um stub + cria o pin `mem.version` (real, com is_file()=True).
    binp = tmp_path / ".claude" / "bin" / "mem"
    binp.parent.mkdir(parents=True)
    binp.write_text("#!/bin/sh\nexit 0\n")
    binp.chmod(0o755)
    pin = binp.parent / "mem.version"
    pin.write_text("0.8.1\n")

    # mem doctor neutro (não interfere no caminho do pin).
    def fake_mem_call(project_root, args, **kw):
        return MemResult(found=True, exit_code=0, stdout="[]", stderr="")

    monkeypatch.setattr(doctor, "mem_call", fake_mem_call)

    # O asset embutido existe (is_file()=True), mas a leitura estoura OSError.
    monkeypatch.setattr(
        doctor, "mem_asset_version_path", lambda: pin  # asset = mesmo path real
    )

    orig_read_text = Path.read_text

    def _boom_read_text(self, *a, **kw):
        if self.name == "mem.version":
            raise OSError(13, "Permission denied")
        return orig_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", _boom_read_text)

    # Não deve crashar: retorna um relatório com um check de pin degradado.
    report = doctor._check_mem(tmp_path)
    pin_check = next(c for c in report.checks if c.name == "pin")
    assert pin_check.status == doctor._STATUS_WARN


def test_check_mem_pin_warns_on_constant_drift(tmp_path, monkeypatch):
    """P7 (cross-AI PR#32): asset==vendored mas != MEM_PINNED_VERSION → WARN.

    A constante `MEM_PINNED_VERSION` agora é a fonte-da-verdade do pin do
    forge; o doctor a valida contra o asset embutido pra pegar drift
    silencioso (era dead constant antes da fix).
    """
    binp = tmp_path / ".claude" / "bin" / "mem"
    binp.parent.mkdir(parents=True)
    binp.write_text("#!/bin/sh\nexit 0\n")
    binp.chmod(0o755)
    # pin vendorizado e asset CONCORDAM entre si, mas divergem da constante.
    drifted = "0.0.0-drift"
    pin = binp.parent / "mem.version"
    pin.write_text(f"{drifted}\n")
    asset = tmp_path / "asset_VERSION"
    asset.write_text(f"{drifted}\n")

    def fake_mem_call(project_root, args, **kw):
        return MemResult(found=True, exit_code=0, stdout="[]", stderr="")

    monkeypatch.setattr(doctor, "mem_call", fake_mem_call)
    monkeypatch.setattr(doctor, "mem_asset_version_path", lambda: asset)

    report = doctor._check_mem(tmp_path)
    pin_check = next(c for c in report.checks if c.name == "pin")
    assert pin_check.status == doctor._STATUS_WARN
    assert doctor.MEM_PINNED_VERSION in (pin_check.message or "")
