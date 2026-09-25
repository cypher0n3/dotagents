"""Deterministic TOML writing for Codex agent files.

Codex agents are flat tables of strings, booleans, and string arrays with one
multi-line prompt, so a small emitter is enough, and unlike a general TOML
writer it can place fixed comment lines between entries.
"""

from __future__ import annotations

import re
from typing import Any

from agentgen.errors import GenerationError

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def _escape(char: str) -> str:
    if char in _ESCAPES:
        return _ESCAPES[char]
    if ord(char) < 0x20 or ord(char) == 0x7F:
        return f"\\u{ord(char):04X}"
    return char


def basic_string(value: str) -> str:
    """Return a single-line TOML basic string."""
    return '"' + "".join(_escape(char) for char in value) + '"'


def multiline_string(value: str) -> str:
    """Return a TOML multi-line basic string that reads back as value exactly."""
    body: list[str] = []
    quotes = 0
    for char in value:
        if char == "\n":
            body.append("\n")
        elif char == '"':
            # Escape every third consecutive quote so no run of three can close the string.
            quotes += 1
            body.append('\\"' if quotes % 3 == 0 else '"')
            continue
        else:
            body.append(_escape(char))
        quotes = 0
    # An unescaped quote just before the closing delimiter would merge into it.
    if body and body[-1] == '"':
        body[-1] = '\\"'
    return '"""\n' + "".join(body) + '"""'


def value(item: Any) -> str:
    """Return one TOML value."""
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, int):
        return str(item)
    if isinstance(item, str):
        return basic_string(item)
    if isinstance(item, list) and all(isinstance(entry, str) for entry in item):
        return "[" + ", ".join(basic_string(entry) for entry in item) + "]"
    raise GenerationError(f"cannot emit {type(item).__name__} as a TOML value")


def entry(key: str, item: Any, *, multiline: bool = False) -> str:
    """Return one top-level ``key = value`` line."""
    if not _BARE_KEY.match(key):
        raise GenerationError(f"cannot emit {key!r} as a TOML key")
    if multiline:
        if not isinstance(item, str):
            raise GenerationError(f"{key}: a multi-line value must be a string")
        return f"{key} = {multiline_string(item)}"
    return f"{key} = {value(item)}"
