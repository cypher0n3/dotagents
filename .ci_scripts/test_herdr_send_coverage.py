#!/usr/bin/env python3
"""Coverage tests for herdr_send.py main block."""

import contextlib
import io
import os
import runpy
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parent.parent / "skills" / "herdr" / "scripts"


class HerdrSendMainBlockTest(unittest.TestCase):
    """Test herdr_send.py when run as script."""

    def test_run_as_main_exits_with_error(self) -> None:
        script_path = SCRIPTS / "herdr_send.py"

        argv = ["herdr_send.py", "check", "coder"]
        with mock.patch.object(sys, "argv", argv):
            with mock.patch.dict(os.environ, {}, clear=True):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        runpy.run_path(str(script_path), run_name="__main__")
        self.assertEqual(raised.exception.code, 14)

    def test_run_as_main_exits_zero(self) -> None:
        script_path = SCRIPTS / "herdr_send.py"

        argv = ["herdr_send.py", "check", "--help"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    runpy.run_path(str(script_path), run_name="__main__")
        self.assertEqual(raised.exception.code, 0)

    def test_import_as_module(self) -> None:
        orig_path = sys.path[:]
        try:
            sys.path.insert(0, str(SCRIPTS))
            import herdr_send
            self.assertTrue(hasattr(herdr_send, "main"))
        finally:
            sys.path[:] = orig_path
            if "herdr_send" in sys.modules:
                del sys.modules["herdr_send"]


if __name__ == "__main__":
    unittest.main()
