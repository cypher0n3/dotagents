#!/usr/bin/env python3
"""Tests for herdr_send message module."""

from __future__ import annotations

import unittest

from herdr_test_support import message

from herdr_lib.exit_codes import EXIT_INVALID_INPUT

MessageError = message.MessageError
format_message = message.format_message
validate_message = message.validate_message


class ValidateMessageTest(unittest.TestCase):
    """Test validate_message."""

    def test_accepts_valid_message(self) -> None:
        self.assertEqual(validate_message("Hello"), "Hello")
        self.assertEqual(validate_message("  Hello  "), "Hello")

    def test_rejects_newlines(self) -> None:
        with self.assertRaises(MessageError) as ctx:
            validate_message("Line 1\nLine 2")
        self.assertEqual(ctx.exception.exit_code, EXIT_INVALID_INPUT)
        self.assertIn("newlines", ctx.exception.message)

    def test_fails_when_empty(self) -> None:
        with self.assertRaises(MessageError) as ctx:
            validate_message("")
        self.assertEqual(ctx.exception.exit_code, EXIT_INVALID_INPUT)
        self.assertIn("empty", ctx.exception.message)

    def test_fails_when_only_whitespace(self) -> None:
        with self.assertRaises(MessageError) as ctx:
            validate_message("   ")
        self.assertEqual(ctx.exception.exit_code, EXIT_INVALID_INPUT)

    def test_fails_when_only_newlines(self) -> None:
        with self.assertRaises(MessageError) as ctx:
            validate_message("\n\n")
        self.assertEqual(ctx.exception.exit_code, EXIT_INVALID_INPUT)
        self.assertIn("only newlines", ctx.exception.message)

    def test_fails_when_contains_control_bytes(self) -> None:
        with self.assertRaises(MessageError) as ctx:
            validate_message("Hello\x00World")
        self.assertEqual(ctx.exception.exit_code, EXIT_INVALID_INPUT)
        self.assertIn("non-printable", ctx.exception.message)

    def test_accepts_tab_and_space(self) -> None:
        msg = "Hello\tWorld test"
        self.assertEqual(validate_message(msg), "Hello\tWorld test")


class FormatMessageTest(unittest.TestCase):
    """Test format_message."""

    def test_formats_with_full_header(self) -> None:
        result = format_message("Hello", "coder", "w1:p1", True, False)
        self.assertIn("From coder", result)
        self.assertIn("pane w1:p1", result)
        self.assertIn("reply expected", result)
        self.assertIn("Hello", result)
        self.assertNotIn("\n", result)

    def test_formats_with_no_reply(self) -> None:
        result = format_message("Hello", "coder", "w1:p1", False, False)
        self.assertIn("From coder", result)
        self.assertIn("pane w1:p1", result)
        self.assertIn("no reply expected", result)
        self.assertIn("Hello", result)
        self.assertNotIn("\n", result)

    def test_fails_when_missing_from_role(self) -> None:
        with self.assertRaises(MessageError) as ctx:
            format_message("Hello", None, "w1:p1", False, False)
        self.assertEqual(ctx.exception.exit_code, EXIT_INVALID_INPUT)
        self.assertIn("required", ctx.exception.message)

    def test_fails_when_missing_pane_id(self) -> None:
        with self.assertRaises(MessageError) as ctx:
            format_message("Hello", "coder", None, False, False)
        self.assertEqual(ctx.exception.exit_code, EXIT_INVALID_INPUT)
        self.assertIn("required", ctx.exception.message)

    def test_returns_text_when_no_header(self) -> None:
        result = format_message("Hello", "coder", "w1:p1", True, True)
        self.assertEqual(result, "Hello")

    def test_formatted_output_never_contains_newline(self) -> None:
        result = format_message("Test message", "operator", "w1:p5", True, False)
        self.assertNotIn("\n", result)


if __name__ == "__main__":
    unittest.main()
