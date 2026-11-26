"""Herdr CLI command runner."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from .errors import SendError
from .exit_codes import EXIT_HERDR_ERROR


class HerdrError(SendError):
    """Herdr command execution error."""

    def __init__(self, message: str):
        super().__init__(EXIT_HERDR_ERROR, message)


class HerdrRunner:
    """Run herdr CLI commands and parse JSON output."""

    def _exec(self, argv: list[str]) -> str:
        """Execute herdr command and return stdout if successful."""
        herdr = shutil.which("herdr")
        if not herdr:
            raise HerdrError("herdr not found in PATH")

        try:
            result = subprocess.run(
                [herdr, *argv],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise HerdrError(f"Failed to execute herdr: {e}") from e

        if result.returncode:
            raise HerdrError(result.stderr.strip() or result.stdout.strip() or "herdr command failed")

        return result.stdout

    def run(self, argv: list[str]) -> dict[str, Any]:
        """Run herdr command and return parsed JSON result."""
        stdout = self._exec(argv)
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            raise HerdrError(f"herdr output is not valid JSON: {e}") from e

    def read_text(self, argv: list[str]) -> str:
        """Run herdr command and return plain text stdout without parsing."""
        return self._exec(argv)

    def send(self, argv: list[str]) -> None:
        """Run herdr send command and check only the return code."""
        self._exec(argv)
