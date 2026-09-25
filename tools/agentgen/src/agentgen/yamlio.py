"""Strict YAML reading and deterministic YAML writing.

Reading rejects duplicate and non-string keys, so a typo cannot silently
replace an earlier value. Writing never passes a whole document to a YAML
serializer: scalars are emitted one at a time, plain when a round trip proves
that is safe and double-quoted otherwise, which keeps the output stable across
PyYAML releases and lets fixed comment lines sit between entries.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError

from agentgen.errors import GenerationError

# First characters that YAML reads as an indicator in a plain scalar.
_INDICATORS = set("-?:,[]{}#&*!|>'\"%@`")
# Characters a plain scalar inside a flow sequence cannot contain.
_FLOW_UNSAFE = set(",[]{}")
KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


class _StrictLoader(yaml.SafeLoader):
    """A safe loader that rejects duplicate and non-string mapping keys."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ConstructorError(None, None, f"mapping key {key!r} is not a string", key_node.start_mark)
        if key in mapping:
            raise ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def read_text(path: Path, label: str) -> str:
    """Return a source file's text, requiring UTF-8 with LF line endings."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise GenerationError(f"{label}: cannot read ({error.strerror})") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GenerationError(f"{label}: not valid UTF-8 ({error.reason})") from error
    if "\r" in text:
        raise GenerationError(f"{label}: uses CR line endings; use LF only")
    if text.startswith("﻿"):
        raise GenerationError(f"{label}: starts with a byte order mark")
    return text


def parse(text: str, label: str) -> Any:
    """Parse YAML source text strictly, reporting problems against label."""
    try:
        return yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - _StrictLoader is a SafeLoader.
    except yaml.YAMLError as error:
        raise GenerationError(f"{label}: invalid YAML: {error}") from error


def load(path: Path, label: str) -> Any:
    """Parse one YAML file strictly."""
    return parse(read_text(path, label), label)


def loads(text: str) -> Any:
    """Parse YAML text strictly, for validating emitted output."""
    return yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - _StrictLoader is a SafeLoader.


def check_text(value: str, label: str, *, multiline: bool = False) -> None:
    """Reject characters that cannot round-trip through every target format."""
    for char in value:
        if char == "\n" and multiline:
            continue
        if not char.isprintable():
            raise GenerationError(f"{label}: contains unsupported character U+{ord(char):04X}")


def _round_trips(text: str, expected: Any) -> bool:
    try:
        return loads(text) == expected
    except yaml.YAMLError:
        return False


def _plain_candidate(value: str, *, flow: bool) -> bool:
    if not value or value != value.strip() or value[0] in _INDICATORS:
        return False
    if ": " in value or " #" in value or value.endswith(":"):
        return False
    return not (flow and _FLOW_UNSAFE.intersection(value))


def scalar(value: Any, *, flow: bool = False) -> str:
    """Return one YAML scalar, plain when that reads back identically."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        raise GenerationError(f"cannot emit {type(value).__name__} as a YAML scalar")
    if _plain_candidate(value, flow=flow):
        probe = f"k: [{value}]" if flow else f"k: {value}"
        if _round_trips(probe, {"k": [value] if flow else value}):
            return value
    quoted = json.dumps(value, ensure_ascii=False)
    if not _round_trips(f"k: {quoted}", {"k": value}):
        raise GenerationError(f"cannot emit {value!r} as a YAML scalar")
    return quoted


def flow_list(values: list[str]) -> str:
    """Return a one-line YAML flow sequence."""
    return "[" + ", ".join(scalar(item, flow=True) for item in values) + "]"


def _key(key: str) -> str:
    if not KEY_PATTERN.match(key):
        raise GenerationError(f"cannot emit {key!r} as a YAML key")
    return key


def entry(key: str, value: Any) -> list[str]:
    """Return the lines for one top-level entry; a list becomes a block sequence."""
    if isinstance(value, list):
        return [f"{_key(key)}:"] + [f"  - {scalar(item)}" for item in value]
    return [f"{_key(key)}: {scalar(value)}"]


def dump_block(value: Any, indent: int = 0) -> list[str]:
    """Return block-style YAML lines for nested mappings, lists, and scalars."""
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict) and item:
                lines.append(f"{pad}{_key(key)}:")
                lines.extend(dump_block(item, indent + 2))
            elif isinstance(item, list) and item:
                lines.append(f"{pad}{_key(key)}:")
                lines.extend(dump_block(item, indent + 2))
            elif isinstance(item, (dict, list)):
                lines.append(f"{pad}{_key(key)}: {'{}' if isinstance(item, dict) else '[]'}")
            elif item is None:
                lines.append(f"{pad}{_key(key)}: null")
            else:
                lines.append(f"{pad}{_key(key)}: {scalar(item)}")
        return lines
    if isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)) and item:
                nested = dump_block(item, indent + 2)
                lines.append(f"{pad}- {nested[0].lstrip()}")
                lines.extend(nested[1:])
            else:
                lines.append(f"{pad}- {scalar(item)}")
        return lines
    raise GenerationError(f"cannot emit {type(value).__name__} as a YAML block")


def dump_document(value: dict) -> str:
    """Return a whole YAML document and prove it reads back identically."""
    text = "\n".join(dump_block(value)) + "\n"
    if loads(text) != value:
        raise GenerationError("emitted YAML does not read back identically")
    return text
