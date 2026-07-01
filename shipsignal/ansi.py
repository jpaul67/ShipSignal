"""Minimal ANSI color helpers for CLI text output.

Color is opt-in at the call site: every helper here takes an explicit
``enabled`` bool rather than reading global state, so renderers stay pure and
testable. :func:`resolve_enabled` is the one place that decides what
``enabled`` should be, so every subcommand applies the same rules:

  * ``--no-color`` (the CLI flag) always wins and disables color.
  * ``NO_COLOR`` env var (any value) disables color.
  * ``FORCE_COLOR`` env var (any value) enables color even when stdout isn't
    a TTY (CI job summaries, screenshot tooling).
  * ``TERM=dumb`` disables color.
  * Otherwise color is on only when the stream is a real TTY.

On Windows, ANSI escapes require VT processing to be enabled on the console
handle; if that fails for any reason, color is silently disabled rather than
printing raw escape codes into the user's terminal.
"""
from __future__ import annotations

import os
import re
import sys

_RESET = "\033[0m"
_BOLD = "\033[1m"
_CODES = {
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
}
# Same green/yellow/red family as GRADE_COLOR in report.py — not the same hex
# values (this is a 16-color terminal palette), just the same intent.
_GRADE_BAND = {"A": "green", "B": "green", "C": "yellow", "D": "red", "F": "red"}

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _win_vt_enabled() -> bool:
    """Best-effort enable of VT100 escape processing on Windows consoles.
    Always True on non-Windows. Never raises — a failure just means no color."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | enable_vt))
    except Exception:
        return False


def resolve_enabled(no_color_flag: bool = False, *, stream=None) -> bool:
    """The single on/off decision every CLI entry point should use before
    passing ``color=`` into a renderer."""
    if no_color_flag or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        # FORCE_COLOR means "emit the codes regardless of what you can detect"
        # (CI log capture, screenshot tooling) — skip the isatty/VT probe.
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    stream = stream if stream is not None else sys.stdout
    try:
        is_tty = stream.isatty()
    except Exception:
        is_tty = False
    return is_tty and _win_vt_enabled()


def paint(text: str, palette_key: str, enabled: bool) -> str:
    """Color ``text`` with a named palette color ("green"/"yellow"/"red"),
    or return it unchanged if disabled or the key isn't in the palette."""
    if not enabled:
        return text
    code = _CODES.get(palette_key, "")
    return f"{code}{text}{_RESET}" if code else text


def grade(text: str, grade_letter: str, enabled: bool) -> str:
    """Color ``text`` by the green/yellow/red band a grade letter falls in."""
    return paint(text, _GRADE_BAND.get(grade_letter, ""), enabled)


def bold(text: str, enabled: bool) -> str:
    return f"{_BOLD}{text}{_RESET}" if enabled else text


def warn(text: str, enabled: bool) -> str:
    return paint(text, "yellow", enabled)


def strip(text: str) -> str:
    """Remove ANSI escape sequences — lets tests compare colored output
    against the plain-text baseline regardless of color state."""
    return _ANSI_RE.sub("", text)
