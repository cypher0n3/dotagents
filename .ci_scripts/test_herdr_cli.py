#!/usr/bin/env python3
"""Tests for herdr_send CLI and commands."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from unittest import mock

from herdr_test_support import FakeRunner

import herdr_send
from herdr_lib.exit_codes import (
    EXIT_HERDR_ERROR,
    EXIT_INVALID_INPUT,
    EXIT_NOT_IN_HERDR,
    EXIT_USAGE_ERROR,
)


class CliInvocationTest(unittest.TestCase):
    """Test CLI entry point and argument parsing."""

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        """Run herdr_send.main with argv; return (exit code, stdout, stderr)."""
        args = ["herdr_send.py", *argv]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", args):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = herdr_send.main()
        return code, out.getvalue(), err.getvalue()

    def test_help(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["herdr_send.py", "--help"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    herdr_send.setup_arg_parser().parse_args()
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("usage:", out.getvalue())

    def test_check_help(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["herdr_send.py", "check", "--help"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    herdr_send.setup_arg_parser().parse_args()
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("usage:", out.getvalue())

    def test_requires_command(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["herdr_send.py"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    herdr_send.setup_arg_parser().parse_args()
        self.assertEqual(ctx.exception.code, EXIT_USAGE_ERROR)
        self.assertIn("required", err.getvalue())

    def test_check_requires_target(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["herdr_send.py", "check"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    herdr_send.setup_arg_parser().parse_args()
        self.assertEqual(ctx.exception.code, EXIT_USAGE_ERROR)
        self.assertIn("required", err.getvalue())

    def test_prompt_requires_text_or_file_or_stdin(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["herdr_send.py", "prompt", "coder"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    herdr_send.setup_arg_parser().parse_args()
        self.assertEqual(ctx.exception.code, EXIT_USAGE_ERROR)
        self.assertIn("required", err.getvalue())

    def test_text_and_file_are_mutually_exclusive(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["herdr_send.py", "prompt", "coder", "--text", "hi", "--file", "x"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    herdr_send.setup_arg_parser().parse_args()
        self.assertEqual(ctx.exception.code, EXIT_USAGE_ERROR)
        self.assertIn("not allowed with argument", err.getvalue())

    def test_empty_text_with_stdin_piped_exits_21(self) -> None:
        runner = FakeRunner()
        with mock.patch.object(sys, "argv", ["herdr_send.py", "prompt", "coder", "--text", ""]):
            with mock.patch.dict(os.environ, {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p9"}, clear=True):
                with mock.patch("sys.stdin", io.StringIO("ignored")):
                    with mock.patch.object(herdr_send, "HerdrRunner", return_value=runner):
                        out, err = io.StringIO(), io.StringIO()
                        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                            code = herdr_send.main()
        self.assertEqual(code, EXIT_INVALID_INPUT)
        self.assertEqual(len(runner.calls), 0)


class MainEntryPointTest(unittest.TestCase):
    """Test main entry point error handling."""

    def test_main_handles_send_error(self) -> None:
        with mock.patch.object(sys, "argv", ["herdr_send.py", "check", "coder"]):
            with mock.patch.dict(os.environ, {}, clear=True):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = herdr_send.main()
        self.assertEqual(code, EXIT_NOT_IN_HERDR)

    def test_main_handles_message_error(self) -> None:
        with mock.patch.object(sys, "argv", ["herdr_send.py", "prompt", "coder", "-", "--no-header"]):
            with mock.patch.dict(os.environ, {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p9"}, clear=True):
                with mock.patch("sys.stdin", io.StringIO("")):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = herdr_send.main()
        self.assertEqual(code, EXIT_INVALID_INPUT)

    def test_main_handles_herdr_error(self) -> None:
        runner = FakeRunner()
        runner.add_error("connection failed")

        with mock.patch.object(herdr_send, "HerdrRunner", return_value=runner):
            with mock.patch.object(sys, "argv", ["herdr_send.py", "check", "coder"]):
                with mock.patch.dict(os.environ, {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p9"}, clear=True):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = herdr_send.main()
        self.assertEqual(code, EXIT_HERDR_ERROR)


if __name__ == "__main__":
    unittest.main()
