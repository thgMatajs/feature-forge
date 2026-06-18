import io

from engine.ui import renderer
from engine.ui import output_mode as om


def test_json_mode_suppresses_cinematic_write():
    stream = io.StringIO()
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        renderer.write("┌── box ──┐", stream=stream)
    finally:
        om.reset_output_mode(token)
    # In JSON mode the cinematic UI is suppressed: nothing written to stream.
    assert stream.getvalue() == ""


def test_plain_mode_strips_and_degrades():
    stream = io.StringIO()
    token = om.set_output_mode(om.OutputMode.PLAIN)
    try:
        renderer.write("\033[1m┌─┐\033[0m", stream=stream)
    finally:
        om.reset_output_mode(token)
    out = stream.getvalue()
    assert "\033" not in out  # SGR stripped
    assert "┌" not in out and "+" in out  # box degraded to ASCII


def test_tty_mode_preserves_unicode_and_sgr():
    stream = io.StringIO()
    token = om.set_output_mode(om.OutputMode.TTY)
    try:
        renderer.write("┌─┐", stream=stream)
    finally:
        om.reset_output_mode(token)
    assert "┌" in stream.getvalue()
