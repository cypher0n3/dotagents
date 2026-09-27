"""Parse the YAML front matter of an agent source in agent_sources/.

Agent sources use a small, predictable part of YAML: block mappings and block
lists nested by indentation, inline lists such as [a, b], plain, single-quoted,
and double-quoted strings, integers, true and false, and comments. Anything
else (anchors, aliases, tags, block scalars, inline mappings) is rejected with
an error rather than guessed at, which is what lets this parser stay small and
dependency-free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SourceError(Exception):
    """A problem that stops generation, reported with the file and line it concerns."""


# Plain words YAML 1.1 readers turn into booleans or null. Rejecting them keeps a
# source from meaning one thing here and another in a full YAML parser.
AMBIGUOUS_WORDS = ("null", "~", "yes", "no", "on", "off", "y", "n", "true", "false")

# Characters that start YAML syntax this parser does not support.
UNSUPPORTED_STARTS = ("&", "*", "!", "|", ">", "{", "%")


@dataclass(frozen=True)
class FrontMatterLine:
    """One front matter line that carries content, ready for parsing."""

    number: int  # line number in the source file, for error messages
    indent: int  # count of leading spaces
    text: str  # the content, without indentation or a trailing comment

    @property
    def is_list_item(self) -> bool:
        return self.text == "-" or self.text.startswith("- ")


def strip_comment(line: str) -> str:
    """Return a line without its trailing `# comment`, leaving `#` inside quotes alone."""
    quote = None
    for index, char in enumerate(line):
        previous = line[index - 1] if index else ""
        if quote:
            # Inside a quoted string; only its closing quote matters. A double
            # quote escaped with a backslash does not close the string.
            escaped = quote == '"' and previous == "\\"
            if char == quote and not escaped:
                quote = None
        elif char in "'\"" and previous in ("", " ", "[", ",", ":"):
            quote = char
        elif char == "#" and previous in ("", " "):
            return line[:index].rstrip()
    return line.rstrip()


class FrontMatterParser:
    """Parse one source file's front matter into dicts, lists, and scalars."""

    def __init__(self, where: str) -> None:
        # `where` names the source file in every error message.
        self.where = where

    def parse(self, text: str) -> tuple[dict[str, object], str]:
        """Split a source into its front matter mapping and its Markdown body."""
        if not text.startswith("---\n"):
            raise SourceError(f"{self.where}: must open with '---' front matter")
        end = text.find("\n---\n", 3)
        if end < 0:
            raise SourceError(f"{self.where}: front matter is not closed with '---'")

        # The front matter sits between the opening '---\n' and the closing
        # '\n---\n'; its first line is line 2 of the file.
        lines = self._content_lines(text[4:end], first_number=2)
        if not lines:
            raise SourceError(f"{self.where}: front matter is empty")
        if lines[0].indent:
            raise SourceError(f"{self.where}:{lines[0].number}: top-level keys must not be indented")

        data, next_index = self._parse_block(lines, 0, indent=0)
        if next_index != len(lines) or not isinstance(data, dict):
            raise SourceError(f"{self.where}: front matter must be a mapping")
        body = text[end + len("\n---\n"):]
        return data, body

    def _content_lines(self, block: str, first_number: int) -> list[FrontMatterLine]:
        """Return the lines that carry content, skipping blank and comment-only lines."""
        lines = []
        for number, raw in enumerate(block.split("\n"), start=first_number):
            leading = raw[: len(raw) - len(raw.lstrip())]
            if "\t" in leading:
                raise SourceError(f"{self.where}:{number}: indent with spaces, not tabs")
            content = strip_comment(raw)
            if not content.strip():
                continue
            indent = len(content) - len(content.lstrip(" "))
            lines.append(FrontMatterLine(number, indent, content.strip()))
        return lines

    def _parse_block(
        self, lines: list[FrontMatterLine], start: int, indent: int
    ) -> tuple[object, int]:
        """Parse the list or mapping whose lines sit at `indent`, starting at `start`.

        Returns the parsed value and the index of the first line after it.
        """
        if lines[start].is_list_item:
            return self._parse_list(lines, start, indent)
        return self._parse_mapping(lines, start, indent)

    def _parse_list(
        self, lines: list[FrontMatterLine], start: int, indent: int
    ) -> tuple[list[object], int]:
        items: list[object] = []
        index = start
        while index < len(lines) and lines[index].indent == indent:
            line = lines[index]
            if not line.is_list_item:
                raise self._error(line, "expected a list item")
            value = line.text[2:].strip()
            if not value:
                raise self._error(line, "nested blocks inside a list are not supported")
            items.append(self._parse_value(value, line))
            index += 1
        return items, index

    def _parse_mapping(
        self, lines: list[FrontMatterLine], start: int, indent: int
    ) -> tuple[dict[str, object], int]:
        mapping: dict[str, object] = {}
        index = start
        while index < len(lines) and lines[index].indent == indent:
            line = lines[index]
            key, colon, rest = line.text.partition(":")
            if not colon or not KEY_PATTERN.match(key) or (rest and not rest.startswith(" ")):
                raise self._error(line, "expected 'key: value'")
            if key in mapping:
                raise self._error(line, f"duplicate key '{key}'")
            index += 1

            value = rest.strip()
            if value:
                mapping[key] = self._parse_value(value, line)
                continue

            # A key with nothing after the colon opens a nested block: deeper
            # lines, or a list whose items sit at the key's own indent.
            following = lines[index] if index < len(lines) else None
            if following is not None and following.indent > indent:
                mapping[key], index = self._parse_block(lines, index, following.indent)
            elif following is not None and following.indent == indent and following.is_list_item:
                mapping[key], index = self._parse_list(lines, index, indent)
            else:
                raise self._error(line, f"'{key}' has no value")

        if index < len(lines) and lines[index].indent > indent:
            raise self._error(lines[index], "unexpected indentation")
        return mapping, index

    def _parse_value(self, raw: str, line: FrontMatterLine) -> object:
        """Parse the value after `key:` or `- `: an inline list or a scalar."""
        if raw.startswith("["):
            if not raw.endswith("]"):
                raise self._error(line, "unterminated inline list")
            return self._parse_inline_list(raw, line)
        return self._parse_scalar(raw, line)

    def _parse_inline_list(self, raw: str, line: FrontMatterLine) -> list[object]:
        """Parse `[a, 'b, c', "d"]`, splitting on commas outside quotes."""
        inner = raw[1:-1].strip()
        if not inner:
            return []
        items: list[str] = []
        current = ""
        quote = None
        for char in inner:
            if quote:
                current += char
                if char == quote:
                    quote = None
            elif char in "'\"":
                quote = char
                current += char
            elif char == ",":
                items.append(current)
                current = ""
            elif char in "[]{}":
                raise self._error(line, "nested collections are not supported in an inline list")
            else:
                current += char
        items.append(current)
        return [self._parse_scalar(item, line) for item in items]

    def _parse_scalar(self, raw: str, line: FrontMatterLine) -> object:
        """Parse one scalar: a quoted or plain string, an integer, or true or false."""
        raw = raw.strip()
        if not raw:
            raise self._error(line, "empty value")
        if raw.startswith(UNSUPPORTED_STARTS):
            raise self._error(line, f"unsupported YAML syntax {raw[:12]!r}")

        if raw.startswith('"'):
            # A JSON string is a valid YAML double-quoted string, and the reverse
            # holds for everything a source needs, so JSON's decoder reads it.
            try:
                value = json.loads(raw)
            except ValueError:
                value = None
            if not isinstance(value, str):
                raise self._error(line, "invalid double-quoted string")
            return value

        if raw.startswith("'"):
            if len(raw) < 2 or not raw.endswith("'"):
                raise self._error(line, "unterminated single-quoted string")
            # In a single-quoted YAML string, '' stands for one quote.
            return raw[1:-1].replace("''", "'")

        if raw == "true":
            return True
        if raw == "false":
            return False
        if raw.lower() in AMBIGUOUS_WORDS:
            raise self._error(line, f"ambiguous value {raw!r}; quote it or use true or false")
        if re.fullmatch(r"-?[0-9]+", raw):
            return int(raw)
        return raw

    def _error(self, line: FrontMatterLine, message: str) -> SourceError:
        return SourceError(f"{self.where}:{line.number}: {message}")


def parse_front_matter(text: str, where: str) -> tuple[dict[str, object], str]:
    """Split a source into its front matter mapping and its body; see FrontMatterParser."""
    return FrontMatterParser(where).parse(text)
