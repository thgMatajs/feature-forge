import pytest
from engine.host.adapter import HostAdapter, HostName, AskKind, AskResult


def test_host_adapter_is_abstract():
    with pytest.raises(TypeError, match="abstract"):
        HostAdapter()


def test_host_name_enum_canonical():
    assert HostName.CLAUDE_CODE.value == "claude-code"
    assert HostName.OPENCODE.value == "opencode"
    assert HostName.TTY.value == "tty"
    assert HostName.INTENT_FILE.value == "intent-file"


def test_ask_kind_enum():
    for k in ("ask", "ask_three_paths", "ask_multi", "ask_text"):
        assert AskKind(k).value == k


def test_ask_result_dataclass_default():
    r = AskResult(value="product")
    assert r.value == "product"
    assert r.from_default is False
    assert r.paused is False
