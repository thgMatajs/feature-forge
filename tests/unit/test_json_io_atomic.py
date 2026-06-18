"""Unit — tempfile namespacing de json_io.write_json (C4 CONC-1).

Valida que o tmp intermediário carrega pid + uuid, sem depender de timing.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.utils import json_io


def test_write_json_uses_per_process_tempfile(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    captured: dict[str, Path] = {}

    real_replace = json_io.os.replace

    def _spy_replace(src, dst):
        captured["tmp"] = Path(src)
        return real_replace(src, dst)

    monkeypatch.setattr(json_io.os, "replace", _spy_replace)
    monkeypatch.setattr(json_io.os, "getpid", lambda: 4242)

    json_io.write_json(target, {"k": "v"})

    tmp_name = captured["tmp"].name
    assert ".4242." in tmp_name, f"tmp deve carregar o pid: {tmp_name}"
    assert tmp_name.endswith(".tmp"), f"tmp deve terminar em .tmp: {tmp_name}"
    # 32 hex chars do uuid4().hex em algum ponto do nome
    assert any(
        len(part) == 32 and all(c in "0123456789abcdef" for c in part)
        for part in tmp_name.split(".")
    ), f"tmp deve carregar uuid4 hex: {tmp_name}"
    # Conteúdo final intacto
    assert json.loads(target.read_text(encoding="utf-8")) == {"k": "v"}
