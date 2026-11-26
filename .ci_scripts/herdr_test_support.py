"""Test support for herdr_send tests."""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).parent.parent / "skills" / "herdr" / "scripts"
sys.path.insert(0, str(SCRIPTS))

runner = importlib.import_module("herdr_lib.runner")
message = importlib.import_module("herdr_lib.message")
checks = importlib.import_module("herdr_lib.checks")
commands = importlib.import_module("herdr_lib.commands")


class FakeRunner:
    """Fake HerdrRunner for offline tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.responses: list[dict[str, Any] | str] = []
        self.errors: list[str | None] = []

    def add_response(self, result: dict[str, Any] | str) -> None:
        """Add a successful response."""
        self.responses.append(result)
        self.errors.append(None)

    def add_error(self, msg: str) -> None:
        """Add an error response."""
        self.responses.append({})
        self.errors.append(msg)

    def run(self, argv: list[str]) -> dict[str, Any]:
        """Record call and return next response or raise error."""
        self.calls.append((argv, {}))
        if not self.responses:
            raise RuntimeError("No response configured")
        result = self.responses.pop(0)
        error = self.errors.pop(0)
        if error:
            raise runner.HerdrError(error)
        if isinstance(result, str):
            raise RuntimeError("Expected dict for run(), got str")
        return result

    def read_text(self, argv: list[str]) -> str:
        """Record call and return next text response or raise error."""
        self.calls.append((argv, {}))
        if not self.responses:
            raise RuntimeError("No response configured")
        result = self.responses.pop(0)
        error = self.errors.pop(0)
        if error:
            raise runner.HerdrError(error)
        if isinstance(result, dict):
            raise RuntimeError("Expected str for read_text(), got dict")
        return result

    def send(self, argv: list[str]) -> None:
        """Record call and check only return code."""
        self.calls.append((argv, {}))
        if not self.responses:
            raise RuntimeError("No response configured")
        self.responses.pop(0)
        error = self.errors.pop(0)
        if error:
            raise runner.HerdrError(error)


EMPTY_SCREEN = "─" * 30 + "\n> \n" + "─" * 30 + "\n"
TYPED_SCREEN = "─" * 30 + "\n> half-typed draft\n" + "─" * 30 + "\n"


class FakeHerdr:
    """Stateful fake herdr: each read sees the screen and state the test set up.

    `screens` is consumed one per pane read and `statuses` one per agent get; the last entry repeats.
    """

    def __init__(self, agents: list[dict[str, Any]] | None = None, screens: list[str] | None = None,
                 statuses: list[str] | None = None) -> None:
        self.agents = agents if agents is not None else [
            {"pane_id": "w1:p1", "name": "coder", "agent": "claude", "agent_session": {"kind": "id"}},
        ]
        self.screens = list(screens or [EMPTY_SCREEN])
        self.statuses = list(statuses or ["idle"])
        self.seq = 10
        self.sent: list[list[str]] = []
        self.calls: list[list[str]] = []
        self.send_error: str | None = None
        self.get_error: str | None = None

    @staticmethod
    def _next(items: list[str]) -> str:
        return items.pop(0) if len(items) > 1 else items[0]

    def run(self, argv: list[str]) -> dict[str, Any]:
        """Answer agent list and agent get."""
        self.calls.append(argv)
        if argv[:2] == ["agent", "list"]:
            return {"result": {"agents": self.agents}}
        if argv[:2] == ["agent", "get"]:
            if self.get_error:
                raise runner.HerdrError(self.get_error)
            status = self._next(self.statuses)
            return {"result": {"agent": {"agent_status": status, "interactive_ready": True,
                                         "state_change_seq": self.seq}}}
        raise RuntimeError(f"unexpected herdr call {argv}")

    def read_text(self, argv: list[str]) -> str:
        """Answer pane read (next screen) and agent read (dialog text)."""
        self.calls.append(argv)
        if argv[:2] == ["agent", "read"]:
            return "Allow this command?"
        return self._next(self.screens)

    def send(self, argv: list[str]) -> None:
        """Record a send; the send itself changes the agent state."""
        self.calls.append(argv)
        if self.send_error:
            raise runner.HerdrError(self.send_error)
        self.sent.append(argv)
        self.seq += 1


class FakeClock:
    """Stand-in for the time module: sleep advances the clock instantly."""

    def __init__(self) -> None:
        # Start at the real time so file mtimes and the fake clock agree.
        self.now = time.time()
        self.sleeps: list[float] = []

    def time(self) -> float:
        """Return the fake current time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance the fake clock."""
        self.sleeps.append(seconds)
        self.now += seconds
