"""Structured result reports for herdr_send: one JSON line by default, YAML on request."""

from __future__ import annotations

import json
import re
from typing import Any

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~"}


def to_json(report: dict[str, Any]) -> str:
    """Render the report as one JSON line."""
    return json.dumps(report, ensure_ascii=False)


def _scalar(value: Any) -> str:
    """Render one YAML scalar; strings are plain only when unambiguous, otherwise double-quoted."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    text = str(value)
    if _PLAIN.match(text) and text.lower() not in _RESERVED:
        return text
    return json.dumps(text, ensure_ascii=False)


def _lines(value: Any, indent: int) -> list[str]:
    """Render a mapping or sequence as indented block YAML lines."""
    pad = "  " * indent
    out: list[str] = []
    items = value.items() if isinstance(value, dict) else ((None, item) for item in value)
    for key, item in items:
        lead = f"{pad}{key}:" if key is not None else f"{pad}-"
        if isinstance(item, (dict, list)) and item:
            if key is None and isinstance(item, dict):
                nested = _lines(item, indent + 1)
                out.append(f"{pad}- {nested[0].lstrip()}")
                out.extend(nested[1:])
            else:
                out.append(lead)
                out.extend(_lines(item, indent + 1))
        elif isinstance(item, (dict, list)):
            out.append(f"{lead} {'{}' if isinstance(item, dict) else '[]'}")
        else:
            out.append(f"{lead} {_scalar(item)}")
    return out


def to_yaml(report: dict[str, Any]) -> str:
    """Render the report as a block YAML document."""
    return "\n".join(_lines(report, 0))


def render(report: dict[str, Any], yaml: bool) -> str:
    """Render the report in the requested format."""
    return to_yaml(report) if yaml else to_json(report)
