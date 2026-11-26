#!/usr/bin/env python3
"""Tests for herdr_send runner module."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from herdr_test_support import runner

HerdrError = runner.HerdrError
HerdrRunner = runner.HerdrRunner


class HerdrRunnerTest(unittest.TestCase):
    """Test HerdrRunner."""

    def test_runs_command_and_parses_json(self) -> None:
        runner = HerdrRunner()
        output = json.dumps({"result": {"status": "ok"}})
        with mock.patch("shutil.which", return_value="/usr/bin/herdr"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout=output, stderr="")
                result = runner.run(["status"])
        self.assertEqual(result, {"result": {"status": "ok"}})
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args[0][0], ["/usr/bin/herdr", "status"])

    def test_fails_when_herdr_not_in_path(self) -> None:
        runner = HerdrRunner()
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(HerdrError) as ctx:
                runner.run(["status"])
            self.assertIn("not found in PATH", ctx.exception.message)

    def test_fails_when_command_returns_nonzero(self) -> None:
        runner = HerdrRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/herdr"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=1, stdout="", stderr="command failed")
                with self.assertRaises(HerdrError) as ctx:
                    runner.run(["bad"])
                self.assertIn("command failed", ctx.exception.message)

    def test_fails_when_output_not_json(self) -> None:
        runner = HerdrRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/herdr"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout="not json", stderr="")
                with self.assertRaises(HerdrError) as ctx:
                    runner.run(["status"])
                self.assertIn("not valid JSON", ctx.exception.message)

    def test_handles_subprocess_error(self) -> None:
        runner = HerdrRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/herdr"):
            with mock.patch("subprocess.run", side_effect=OSError("exec failed")):
                with self.assertRaises(HerdrError) as ctx:
                    runner.run(["status"])
                self.assertIn("Failed to execute", ctx.exception.message)

    def test_read_text_returns_plain_text(self) -> None:
        runner = HerdrRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/herdr"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout="plain text output", stderr="")
                result = runner.read_text(["pane", "read", "w1:p1"])
        self.assertEqual(result, "plain text output")

    def test_send_succeeds_with_empty_stdout(self) -> None:
        runner = HerdrRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/herdr"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                runner.send(["agent", "prompt", "w1:p1", "test"])

    def test_send_fails_on_nonzero_exit(self) -> None:
        runner = HerdrRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/herdr"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=1, stdout="", stderr="command failed")
                with self.assertRaises(HerdrError) as ctx:
                    runner.send(["agent", "prompt", "w1:p1", "test"])
                self.assertIn("command failed", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
