#!/usr/bin/env python3
"""Offline tests of the TUI profiles against screen shapes seen on live herdr 0.9.5 panes."""

from __future__ import annotations

import unittest

from herdr_test_support import FakeRunner

from herdr_lib.checks import check_input_empty, resolve_target
from herdr_lib.errors import SendError
from herdr_lib.exit_codes import EXIT_BUSY

RULE = "─" * 60

CLAUDE_TITLED = "\n".join([
    "✻ Worked for 30s",
    "",
    RULE + " CONTROL ─",
    "❯ ",
    RULE,
    "  [projects] {Opus · medium} | ctx ━━╌╌╌╌╌╌╌╌ 15% | 7d 30%",
    "  ⏵⏵ auto mode on · 1 shell · ↓ to manage",
])

CURSOR_IDLE = "\n".join([
    "  REVIEW DONE",
    "",
    "  → Add a follow-up",
    "",
    "",
    "  [repo] (main) {Auto} | ctx ━━━━╌╌╌╌╌╌ 40% | models 85% used | api 95% used",
])

CURSOR_WORKING = "\n".join([
    " ⠠⠛ Thinking  86.28k tokens",
    "",
    "  → Add a follow-up" + " " * 60 + "ctrl+c to stop",
    "",
    "",
    "  [repo] {Auto} | ctx ━━━━━━━━╌╌ 89% | models 85% used | api 95% used",
])

CODEX_IDLE = "\n".join([
    "• Working (4h 00m 38s • esc to interrupt)",
    "",
    "",
    "› Ask Codex to do anything",
    "",
    "  GPT-6 medium · repo · main · Context 10% used · weekly 87% left · Main [default]",
    "  ← for agents · ? for shortcuts" + " " * 40 + "⚠ 2 warnings · f2 to view",
])


AGY_HINTS = [
    "Auto mode: edits & safe commands auto-approved (shift+tab to cycle)",
    "Plan mode: research & plan only (shift+tab to cycle)",
    "Accept-edits mode: file edits auto-approved (shift+tab to cycle)",
]


def agy_screen(input_row: str) -> str:
    """Build an agy screen whose framed input box holds one row."""
    return "\n".join([RULE, "> " + input_row, RULE, "? for shortcuts" + " " * 40 + "auto · Gemini 4 Neon · low"])


def check(screen: str, kind: str) -> None:
    """Run check_input_empty on one synthetic screen."""
    runner = FakeRunner()
    runner.add_response(screen)
    check_input_empty(runner, "w1:p1", kind, None)


class ResolveRealAgentShapeTest(unittest.TestCase):
    """herdr reports the TUI in "agent"; agent_session.kind is "id"."""

    def test_reads_kind_from_agent_field(self) -> None:
        runner = FakeRunner()
        runner.add_response({"result": {"agents": [{
            "pane_id": "w1:p1",
            "name": "reviewer",
            "agent": "cursor",
            "agent_session": {"agent": "cursor", "kind": "id", "source": "herdr:cursor"},
        }]}})
        self.assertEqual(resolve_target(runner, "reviewer", None, None)[2], "cursor")


class ProfileTest(unittest.TestCase):
    """Each profile accepts its real empty screen and refuses typed text."""

    def assert_busy(self, screen: str, kind: str) -> None:
        """Assert the screen is refused as busy."""
        with self.assertRaises(SendError) as ctx:
            check(screen, kind)
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)

    def test_claude_titled_rule_is_a_frame(self) -> None:
        check(CLAUDE_TITLED, "claude")

    def test_claude_titled_rule_with_text_is_busy(self) -> None:
        self.assert_busy(CLAUDE_TITLED.replace("❯ ", "❯ /comp"), "claude")

    def test_cursor_idle_and_working_are_empty(self) -> None:
        check(CURSOR_IDLE, "cursor")
        check(CURSOR_WORKING, "cursor")

    def test_cursor_typed_text_is_busy(self) -> None:
        self.assert_busy(CURSOR_IDLE.replace("Add a follow-up", "fix the gate"), "cursor")

    def test_cursor_wrapped_text_below_prompt_is_busy(self) -> None:
        self.assert_busy(CURSOR_IDLE.replace("  → Add a follow-up\n", "  → first line\n  second line\n"), "cursor")

    def test_cursor_without_prompt_row_is_busy(self) -> None:
        self.assert_busy(CURSOR_IDLE.replace("  → Add a follow-up", ""), "cursor")

    def test_codex_placeholder_is_empty(self) -> None:
        check(CODEX_IDLE, "codex")

    def test_fresh_session_placeholders_are_empty(self) -> None:
        check(CLAUDE_TITLED.replace("❯ ", '❯ Try "write a test for <filepath>"'), "claude")
        check(CURSOR_IDLE.replace("Add a follow-up", "Plan, search, build anything"), "cursor")
        check(CODEX_IDLE.replace(" · repo · main · Context", " · Context"), "codex")

    def test_agy_mode_hints_are_empty(self) -> None:
        for hint in AGY_HINTS:
            check(agy_screen(hint), "agy")

    def test_agy_typed_text_is_busy(self) -> None:
        self.assert_busy(agy_screen("typed draft"), "agy")
        self.assert_busy(agy_screen(AGY_HINTS[0] + " and more"), "agy")

    def test_cursor_trust_dialog_is_busy(self) -> None:
        # herdr reported this pane idle; only the screen check stops the send.
        dialog = "\n".join([
            "  ╭" + "─" * 40 + "╮",
            "  │  ▶ [a] Trust this workspace" + " " * 12 + "│",
            "  │    [q] Quit" + " " * 28 + "│",
            "  ╰" + "─" * 40 + "╯",
        ])
        self.assert_busy(dialog, "cursor")

    def test_codex_typed_text_is_busy(self) -> None:
        self.assert_busy(CODEX_IDLE.replace("Ask Codex to do anything", "run the tests"), "codex")

    def test_codex_unverified_placeholder_is_busy(self) -> None:
        self.assert_busy(CODEX_IDLE.replace("Ask Codex to do anything", "Explain this codebase"), "codex")

    def test_codex_transcript_prompt_above_uses_last_row(self) -> None:
        self.assert_busy("› earlier message\n" + CODEX_IDLE.replace("› Ask Codex to do anything", "› typed"), "codex")
        check("› earlier message\nreply text\n" + CODEX_IDLE, "codex")


if __name__ == "__main__":
    unittest.main()
