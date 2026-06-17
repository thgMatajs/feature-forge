import pytest
from engine.host.registry import register, get_adapter_class, clear_registry
from engine.host.adapter import HostName, HostAdapter


def test_register_and_get(monkeypatch):
    class StubAdapter(HostAdapter):
        name = HostName.TTY
        def ask(self, **kw): ...
        def ask_text(self, **kw): ...
        def ask_multi(self, **kw): ...
        def emit_progress(self, **kw): ...
        def emit_warn(self, **kw): ...
    clear_registry()
    register(HostName.TTY, StubAdapter)
    assert get_adapter_class(HostName.TTY) is StubAdapter


def test_get_unknown_raises():
    clear_registry()
    with pytest.raises(KeyError):
        get_adapter_class(HostName.OPENCODE)
