#!/usr/bin/env python3
"""Tests for herdr_send checks module."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from herdr_test_support import FakeRunner

from herdr_lib.checks import (
    check_herdr_env,
    check_input_empty,
    check_not_blocked,
    check_state_allowed,
    find_input_frame,
    get_agent_snapshot,
    list_agents,
    load_tui_profile,
    read_visible_screen,
    resolve_target,
    verify_state_unchanged,
)
from herdr_lib.errors import SendError
from herdr_lib.exit_codes import (
    EXIT_BLOCKED,
    EXIT_BUSY,
    EXIT_HERDR_ERROR,
    EXIT_NOT_IN_HERDR,
    EXIT_TARGET_ERROR,
    EXIT_WORKING_REFUSED,
)


class CheckHerdrEnvTest(unittest.TestCase):
    """Test check_herdr_env."""

    def test_passes_when_env_set(self) -> None:
        with mock.patch.dict(os.environ, {"HERDR_ENV": "1"}):
            check_herdr_env()

    def test_fails_when_env_missing(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SendError) as ctx:
                check_herdr_env()
            self.assertEqual(ctx.exception.exit_code, EXIT_NOT_IN_HERDR)

    def test_fails_when_env_wrong_value(self) -> None:
        with mock.patch.dict(os.environ, {"HERDR_ENV": "0"}):
            with self.assertRaises(SendError) as ctx:
                check_herdr_env()
            self.assertEqual(ctx.exception.exit_code, EXIT_NOT_IN_HERDR)


class ListAgentsTest(unittest.TestCase):
    """Test list_agents."""

    def test_returns_agents_list(self) -> None:
        runner = FakeRunner()
        runner.add_response({"result": {"agents": [{"pane_id": "w1:p1"}]}})
        agents = list_agents(runner)
        self.assertEqual(agents, [{"pane_id": "w1:p1"}])

    def test_handles_herdr_error(self) -> None:
        runner = FakeRunner()
        runner.add_error("connection failed")
        with self.assertRaises(SendError) as ctx:
            list_agents(runner)
        self.assertEqual(ctx.exception.exit_code, EXIT_HERDR_ERROR)


class ResolveTargetTest(unittest.TestCase):
    """Test resolve_target."""

    def test_fails_when_no_agents(self) -> None:
        runner = FakeRunner()
        runner.add_response({"result": {"agents": []}})
        with self.assertRaises(SendError) as ctx:
            resolve_target(runner, "coder", None, None)
        self.assertEqual(ctx.exception.exit_code, EXIT_TARGET_ERROR)
        self.assertIn("No agents found", ctx.exception.message)

    def test_resolves_by_pane_id(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agents": [
                    {"pane_id": "w1:p1", "name": "coder", "agent": "claude", "agent_session": {"kind": "id"}},
                ],
            },
        })
        pane_id, name, kind = resolve_target(runner, "w1:p1", None, None)
        self.assertEqual(pane_id, "w1:p1")
        self.assertEqual(name, "coder")
        self.assertEqual(kind, "claude")

    def test_resolves_by_name(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agents": [
                    {"pane_id": "w1:p1", "name": "coder", "agent": "codex", "agent_session": {"kind": "id"}},
                ],
            },
        })
        pane_id, name, kind = resolve_target(runner, "coder", None, None)
        self.assertEqual(pane_id, "w1:p1")
        self.assertEqual(kind, "codex")

    def test_fails_when_not_found(self) -> None:
        runner = FakeRunner()
        runner.add_response({"result": {"agents": [{"pane_id": "w1:p1", "name": "other"}]}})
        with self.assertRaises(SendError) as ctx:
            resolve_target(runner, "coder", None, None)
        self.assertEqual(ctx.exception.exit_code, EXIT_TARGET_ERROR)
        self.assertIn("not found", ctx.exception.message)

    def test_fails_when_ambiguous(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agents": [
                    {"pane_id": "w1:p1", "name": "coder"},
                    {"pane_id": "w1:p2", "name": "coder"},
                ],
            },
        })
        with self.assertRaises(SendError) as ctx:
            resolve_target(runner, "coder", None, None)
        self.assertEqual(ctx.exception.exit_code, EXIT_TARGET_ERROR)
        self.assertIn("matches 2", ctx.exception.message)

    def test_fails_when_own_pane(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agents": [
                    {"pane_id": "w1:p1", "name": "self"},
                ],
            },
        })
        with self.assertRaises(SendError) as ctx:
            resolve_target(runner, "w1:p1", None, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_TARGET_ERROR)
        self.assertIn("own pane", ctx.exception.message)

    def test_fails_when_kind_mismatch(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agents": [
                    {"pane_id": "w1:p1", "name": "coder", "agent": "claude", "agent_session": {"kind": "id"}},
                ],
            },
        })
        with self.assertRaises(SendError) as ctx:
            resolve_target(runner, "coder", "xorc", None)
        self.assertEqual(ctx.exception.exit_code, EXIT_TARGET_ERROR)
        self.assertIn("Expected kind", ctx.exception.message)

    def test_skips_agents_without_pane_id(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agents": [
                    {"name": "coder"},
                    {"pane_id": "w1:p1", "name": "coder", "agent": "claude", "agent_session": {"kind": "id"}},
                ],
            },
        })
        pane_id, _, _ = resolve_target(runner, "coder", None, None)
        self.assertEqual(pane_id, "w1:p1")


class GetAgentSnapshotTest(unittest.TestCase):
    """Test get_agent_snapshot."""

    def test_returns_agent_data(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agent": {
                    "pane_id": "w1:p1",
                    "agent_status": "idle",
                    "interactive_ready": True,
                    "state_change_seq": 42,
                },
            },
        })
        agent = get_agent_snapshot(runner, "w1:p1")
        self.assertEqual(agent["agent_status"], "idle")
        self.assertEqual(agent["state_change_seq"], 42)

    def test_fails_when_no_agent_data(self) -> None:
        runner = FakeRunner()
        runner.add_response({"result": {}})
        with self.assertRaises(SendError) as ctx:
            get_agent_snapshot(runner, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_HERDR_ERROR)

    def test_allows_missing_interactive_ready(self) -> None:
        # herdr 0.9.5 omits interactive_ready for some live Claude panes.
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agent": {
                    "agent_status": "idle",
                    "state_change_seq": 42,
                },
            },
        })
        agent = get_agent_snapshot(runner, "w1:p1")
        self.assertNotIn("interactive_ready", agent)
        check_state_allowed(agent, disable_working=False)

    def test_fails_when_missing_state_change_seq(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agent": {
                    "agent_status": "idle",
                    "interactive_ready": True,
                },
            },
        })
        with self.assertRaises(SendError) as ctx:
            get_agent_snapshot(runner, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_WORKING_REFUSED)
        self.assertIn("state_change_seq", ctx.exception.message)

    def test_fails_when_missing_agent_status(self) -> None:
        runner = FakeRunner()
        runner.add_response({
            "result": {
                "agent": {
                    "interactive_ready": True,
                    "state_change_seq": 42,
                },
            },
        })
        with self.assertRaises(SendError) as ctx:
            get_agent_snapshot(runner, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_WORKING_REFUSED)
        self.assertIn("agent_status", ctx.exception.message)

    def test_fails_when_herdr_error(self) -> None:
        runner = FakeRunner()
        runner.add_error("connection failed")
        with self.assertRaises(SendError) as ctx:
            get_agent_snapshot(runner, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_HERDR_ERROR)
        self.assertIn("Failed to get agent state", ctx.exception.message)


class CheckNotBlockedTest(unittest.TestCase):
    """Test check_not_blocked."""

    def test_passes_when_not_blocked(self) -> None:
        runner = FakeRunner()
        agent = {"agent_status": "idle"}
        check_not_blocked(agent, runner, "w1:p1")

    def test_fails_when_blocked(self) -> None:
        runner = FakeRunner()
        runner.add_response("Approve this change?")
        agent = {"agent_status": "blocked"}
        with self.assertRaises(SendError) as ctx:
            check_not_blocked(agent, runner, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_BLOCKED)
        self.assertIn("Approve", ctx.exception.message)

    def test_handles_read_failure(self) -> None:
        runner = FakeRunner()
        runner.add_error("read failed")
        agent = {"agent_status": "blocked"}
        with self.assertRaises(SendError) as ctx:
            check_not_blocked(agent, runner, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_BLOCKED)
        self.assertIn("unavailable", ctx.exception.message)


class CheckStateAllowedTest(unittest.TestCase):
    """Test check_state_allowed."""

    def test_passes_when_idle(self) -> None:
        agent = {"agent_status": "idle", "interactive_ready": True}
        check_state_allowed(agent, disable_working=False)

    def test_passes_when_working_and_allowed(self) -> None:
        agent = {"agent_status": "working", "interactive_ready": True}
        check_state_allowed(agent, disable_working=False)

    def test_fails_when_unknown(self) -> None:
        agent = {"agent_status": "unknown", "interactive_ready": True}
        with self.assertRaises(SendError) as ctx:
            check_state_allowed(agent, disable_working=False)
        self.assertEqual(ctx.exception.exit_code, EXIT_WORKING_REFUSED)
        self.assertIn("unknown", ctx.exception.message)

    def test_fails_when_not_interactive_ready(self) -> None:
        agent = {"agent_status": "idle", "interactive_ready": False}
        with self.assertRaises(SendError) as ctx:
            check_state_allowed(agent, disable_working=False)
        self.assertEqual(ctx.exception.exit_code, EXIT_WORKING_REFUSED)
        self.assertIn("not interactive_ready", ctx.exception.message)

    def test_fails_when_working_and_disabled(self) -> None:
        agent = {"agent_status": "working", "interactive_ready": True}
        with self.assertRaises(SendError) as ctx:
            check_state_allowed(agent, disable_working=True)
        self.assertEqual(ctx.exception.exit_code, EXIT_WORKING_REFUSED)
        self.assertIn("working", ctx.exception.message)


class VerifyStateUnchangedTest(unittest.TestCase):
    """Test verify_state_unchanged."""

    def test_passes_when_unchanged(self) -> None:
        agent = {"state_change_seq": 42}
        verify_state_unchanged(agent, 42)

    def test_fails_when_changed(self) -> None:
        agent = {"state_change_seq": 43}
        with self.assertRaises(SendError) as ctx:
            verify_state_unchanged(agent, 42)
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)
        self.assertIn("42 -> 43", ctx.exception.message)


class LoadTuiProfileTest(unittest.TestCase):
    """Test load_tui_profile."""

    def test_loads_profile_by_kind(self) -> None:
        profile = load_tui_profile("claude", None)
        self.assertIn("frame_rule_regex", profile)
        self.assertIn("idle_chrome_patterns", profile)

    def test_loads_profile_by_override(self) -> None:
        profile = load_tui_profile("claude", "xorc")
        self.assertIn("frame_rule_regex", profile)

    def test_fails_when_profile_not_found(self) -> None:
        with self.assertRaises(SendError) as ctx:
            load_tui_profile("unknown", None)
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)
        self.assertIn("No TUI profile", ctx.exception.message)


class ReadVisibleScreenTest(unittest.TestCase):
    """Test read_visible_screen."""

    def test_returns_lines(self) -> None:
        runner = FakeRunner()
        runner.add_response("line1\nline2")
        lines = read_visible_screen(runner, "w1:p1")
        self.assertEqual(lines, ["line1", "line2"])

    def test_handles_read_error(self) -> None:
        runner = FakeRunner()
        runner.add_error("read failed")
        with self.assertRaises(SendError) as ctx:
            read_visible_screen(runner, "w1:p1")
        self.assertEqual(ctx.exception.exit_code, EXIT_HERDR_ERROR)


class FindInputFrameTest(unittest.TestCase):
    """Test find_input_frame."""

    def test_finds_frame_between_rules(self) -> None:
        lines = [
            "output",
            "──────────────────────",
            "> ",
            "──────────────────────",
            "more output",
        ]
        frame = find_input_frame(lines, r"^[─━=]{20,}$")
        self.assertEqual(frame, ["> "])

    def test_fails_when_fewer_than_two_rules(self) -> None:
        lines = ["──────────────────────", "> "]
        with self.assertRaises(SendError) as ctx:
            find_input_frame(lines, r"^[─━=]{20,}$")
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)
        self.assertIn("No input frame", ctx.exception.message)

    def test_fails_when_frame_is_empty(self) -> None:
        lines = [
            "──────────────────────",
            "──────────────────────",
            "output",
        ]
        with self.assertRaises(SendError) as ctx:
            find_input_frame(lines, r"^[─━=]{20,}$")
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)


class CheckInputEmptyTest(unittest.TestCase):
    """Test check_input_empty."""

    def test_passes_when_input_empty(self) -> None:
        runner = FakeRunner()
        runner.add_response("──────────────────────\n> \n──────────────────────\n")
        check_input_empty(runner, "w1:p1", "claude", None)

    def test_passes_with_known_chrome(self) -> None:
        runner = FakeRunner()
        runner.add_response("──────────────────────\n> \n❯ \nModel: claude-4\n──────────────────────\n")
        check_input_empty(runner, "w1:p1", "claude", None)

    def test_fails_when_input_has_text(self) -> None:
        runner = FakeRunner()
        runner.add_response("──────────────────────\n> \n/goal-dire\n──────────────────────\n")
        with self.assertRaises(SendError) as ctx:
            check_input_empty(runner, "w1:p1", "claude", None)
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)
        self.assertIn("unsubmitted text", ctx.exception.message)

    def test_fails_on_half_typed_slash_command(self) -> None:
        runner = FakeRunner()
        runner.add_response("──────────────────────\n> \n/comp\n──────────────────────\n")
        with self.assertRaises(SendError) as ctx:
            check_input_empty(runner, "w1:p1", "claude", None)
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)


if __name__ == "__main__":
    unittest.main()
