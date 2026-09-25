"""Tests for the YAML and TOML emitters."""

from __future__ import annotations

import tomllib
import unittest

from agentgen import tomlio, yamlio
from agentgen.errors import GenerationError

HOSTILE = [
    "---",
    "--- evil: true",
    "{{ secret }} and {% include 'x' %}",
    "value # not a comment",
    "key: value",
    "- item",
    "[a, b]",
    "true",
    "null",
    "0123",
    "1e3",
    "'quoted'",
    '"double"',
    "trailing colon:",
    "back\\slash",
    "*alias",
    "&anchor",
    "!tag",
    "@at",
    "%percent",
    " leading space",
    "yes",
    "~",
]


class YamlScalarTest(unittest.TestCase):
    def test_plain_when_safe(self) -> None:
        self.assertEqual(yamlio.scalar("Read, Grep, Glob, Bash"), "Read, Grep, Glob, Bash")
        self.assertEqual(yamlio.scalar("the repository's conventions"), "the repository's conventions")

    def test_hostile_strings_stay_scalar_data(self) -> None:
        for value in HOSTILE:
            with self.subTest(value=value):
                self.assertEqual(yamlio.loads(f"k: {yamlio.scalar(value)}"), {"k": value})
                self.assertEqual(yamlio.loads(f"k: {yamlio.flow_list([value, 'x'])}"), {"k": [value, "x"]})

    def test_booleans_and_integers(self) -> None:
        self.assertEqual(yamlio.scalar(True), "true")
        self.assertEqual(yamlio.scalar(3), "3")

    def test_block_entry(self) -> None:
        self.assertEqual(yamlio.entry("skills", ["a", "b"]), ["skills:", "  - a", "  - b"])

    def test_rejects_bad_key(self) -> None:
        with self.assertRaises(GenerationError):
            yamlio.entry("bad key", "x")

    def test_check_text_rejects_control_characters(self) -> None:
        for char in ("\x00", "\x7f", "\u0085", " ", "﻿", "\t"):
            with self.subTest(char=repr(char)), self.assertRaises(GenerationError):
                yamlio.check_text(f"a{char}b", "label")
        yamlio.check_text("line one\nline two", "label", multiline=True)
        with self.assertRaises(GenerationError):
            yamlio.check_text("line one\nline two", "label")


class YamlDocumentTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        document = {"a": {"b": [1, "two", {"c": "d: e", "f": []}], "g": {}}, "h": None, "i": ["x"]}
        self.assertEqual(yamlio.loads(yamlio.dump_document(document)), document)

    def test_deterministic(self) -> None:
        document = {"z": 1, "a": ["b", {"c": "d"}]}
        self.assertEqual(yamlio.dump_document(document), yamlio.dump_document(document))

    def test_strict_loader_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(Exception):
            yamlio.loads("a: 1\na: 2\n")

    def test_strict_loader_rejects_non_string_keys(self) -> None:
        with self.assertRaises(Exception):
            yamlio.loads("1: a\n")


class TomlTest(unittest.TestCase):
    CASES = [
        "plain text\n",
        'a " quote',
        'two "" quotes',
        'three """ quotes',
        'six """""" quotes',
        'ends with a quote"',
        'ends with two quotes""',
        'ends with three quotes"""',
        "back\\slash at end\\",
        "control \x01 and \x7f and tab\t",
        "\nleading newline",
        "\n\n",
        "",
        "unicode é \U0001F600",
    ]

    def test_multiline_round_trip(self) -> None:
        for value in self.CASES:
            with self.subTest(value=value):
                text = tomlio.entry("k", value, multiline=True)
                self.assertEqual(tomllib.loads(text), {"k": value})

    def test_basic_round_trip(self) -> None:
        for value in self.CASES:
            with self.subTest(value=value):
                self.assertEqual(tomllib.loads(tomlio.entry("k", value)), {"k": value})

    def test_values(self) -> None:
        text = "\n".join([tomlio.entry("a", True), tomlio.entry("b", ["x", 'y"']), tomlio.entry("c", 4)])
        self.assertEqual(tomllib.loads(text), {"a": True, "b": ["x", 'y"'], "c": 4})

    def test_rejects_bad_key(self) -> None:
        with self.assertRaises(GenerationError):
            tomlio.entry("a.b", "x")


if __name__ == "__main__":
    unittest.main()
