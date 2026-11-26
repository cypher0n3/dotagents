"""Herdr safe-send validation checks."""

from __future__ import annotations

import functools
import json
import os
import re
from pathlib import Path
from typing import Any

from .errors import SendError
from .exit_codes import (
    EXIT_BLOCKED,
    EXIT_BUSY,
    EXIT_HERDR_ERROR,
    EXIT_NOT_IN_HERDR,
    EXIT_TARGET_ERROR,
    EXIT_WORKING_REFUSED,
)
from .runner import HerdrError, HerdrRunner

_PROFILES_PATH = Path(__file__).parent.parent.parent / "assets" / "tui-profiles.json"


def check_herdr_env() -> None:
    """Check HERDR_ENV=1 is set."""
    if os.environ.get("HERDR_ENV") != "1":
        raise SendError(EXIT_NOT_IN_HERDR, "Not running inside Herdr (HERDR_ENV != 1)")


def list_agents(runner: HerdrRunner) -> list[dict[str, Any]]:
    """List agents via herdr agent list."""
    try:
        result = runner.run(["agent", "list"])
    except HerdrError as e:
        raise SendError(EXIT_HERDR_ERROR, f"Failed to list agents: {e.message}") from e
    return result.get("result", {}).get("agents", [])


def _build_agent_list(agents: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """Build list of (pane_id, name, kind) tuples from agent data."""
    result = []
    for agent in agents:
        pane_id = agent.get("pane_id")
        if not pane_id:
            continue
        name = agent.get("name") or ""
        # herdr reports the TUI in "agent"; agent_session.kind is the session id type ("id").
        agent_session = agent.get("agent_session") or {}
        kind = agent.get("agent") or agent_session.get("agent") or ""
        result.append((pane_id, name, kind))
    return result


def _find_matching_agents(
    agent_list: list[tuple[str, str, str]],
    target: str,
) -> list[tuple[str, str, str]]:
    """Find agents matching target by pane_id or name."""
    return [
        (pane_id, name, kind)
        for pane_id, name, kind in agent_list
        if pane_id == target or (name and name == target)
    ]


def _validate_resolved_target(
    pane_id: str,
    agent_kind: str,
    expect_kind: str | None,
    own_pane: str | None,
) -> None:
    """Validate resolved target against constraints."""
    if pane_id == own_pane:
        raise SendError(EXIT_TARGET_ERROR, "Cannot send to own pane")

    if expect_kind and agent_kind != expect_kind:
        raise SendError(
            EXIT_TARGET_ERROR,
            f"Expected kind '{expect_kind}' but target is '{agent_kind}'",
        )


def resolve_target(
    runner: HerdrRunner,
    target: str,
    expect_kind: str | None,
    own_pane: str | None,
) -> tuple[str, str, str]:
    """Resolve target to pane ID, name, and agent kind."""
    agents = list_agents(runner)
    if not agents:
        raise SendError(EXIT_TARGET_ERROR, "No agents found")

    agent_list = _build_agent_list(agents)
    candidates = _find_matching_agents(agent_list, target)

    if not candidates:
        raise SendError(EXIT_TARGET_ERROR, f"Target '{target}' not found")

    if len(candidates) > 1:
        raise SendError(
            EXIT_TARGET_ERROR,
            f"Target '{target}' matches {len(candidates)} agents; be more specific",
        )

    pane_id, name, agent_kind = candidates[0]
    _validate_resolved_target(pane_id, agent_kind, expect_kind, own_pane)

    return pane_id, name, agent_kind


def get_agent_snapshot(runner: HerdrRunner, pane_id: str) -> dict[str, Any]:
    """Get agent snapshot via herdr agent get."""
    try:
        result = runner.run(["agent", "get", pane_id])
    except HerdrError as e:
        raise SendError(EXIT_HERDR_ERROR, f"Failed to get agent state: {e.message}") from e

    agent = result.get("result", {}).get("agent", {})
    if not agent:
        raise SendError(EXIT_HERDR_ERROR, "No agent data returned")

    if "state_change_seq" not in agent:
        raise SendError(EXIT_WORKING_REFUSED, "Agent missing state_change_seq field; refusing send", "missing_field")

    if "agent_status" not in agent:
        raise SendError(EXIT_WORKING_REFUSED, "Agent missing agent_status field; refusing send", "missing_field")

    return agent


def check_not_blocked(agent: dict[str, Any], runner: HerdrRunner, pane_id: str) -> None:
    """Check agent is not blocked."""
    status = agent.get("agent_status")

    if status == "blocked":
        try:
            dialog = runner.read_text(["agent", "read", pane_id, "--source", "recent-unwrapped", "--lines", "50"])
        except HerdrError:
            dialog = "(dialog unavailable)"

        raise SendError(
            EXIT_BLOCKED,
            f"Agent is blocked (approval or question dialog showing):\n{dialog}",
            "blocked",
        )


def check_state_allowed(agent: dict[str, Any], disable_working: bool) -> None:
    """Check agent state is allowed for send."""
    status = agent.get("agent_status")

    if status == "unknown":
        raise SendError(EXIT_WORKING_REFUSED, "Agent state is unknown; refusing send", "unknown_state")

    # herdr omits interactive_ready for some live panes; only an explicit false refuses.
    # The visible-screen check still has to prove the input box is empty.
    if agent.get("interactive_ready") is False:
        raise SendError(EXIT_WORKING_REFUSED, "Agent is not interactive_ready; refusing send", "not_interactive_ready")

    if status == "working" and disable_working:
        raise SendError(
            EXIT_WORKING_REFUSED,
            "Agent is working; refusing send (default allows working, message queues)",
            "working",
        )


def verify_state_unchanged(agent: dict[str, Any], expected_seq: int) -> None:
    """Verify state_change_seq has not changed since checks."""
    current_seq = agent.get("state_change_seq")

    if current_seq != expected_seq:
        raise SendError(
            EXIT_BUSY,
            f"Agent state changed during checks (seq {expected_seq} -> {current_seq}); refusing send",
            "state_changed",
        )


@functools.cache
def load_profiles() -> dict[str, Any]:
    """Load TUI profiles from assets once."""
    with open(_PROFILES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_tui_profile(agent_kind: str, tui_override: str | None) -> dict[str, Any]:
    """Load TUI profile from assets."""
    profiles = load_profiles()

    tui_name = tui_override if tui_override else agent_kind
    profile = profiles.get(tui_name)

    if not profile:
        raise SendError(
            EXIT_BUSY,
            f"No TUI profile for '{tui_name}'; cannot verify input is empty (fail closed)",
            "no_profile",
        )

    return profile


def read_visible_screen(runner: HerdrRunner, pane_id: str) -> list[str]:
    """Read visible screen content."""
    try:
        output = runner.read_text(["pane", "read", pane_id, "--source", "visible"])
    except HerdrError as e:
        raise SendError(EXIT_HERDR_ERROR, f"Failed to read pane: {e.message}") from e

    return output.splitlines()


def find_input_frame(lines: list[str], frame_rule_regex: str) -> list[str]:
    """Find input frame from last two rule lines."""
    frame_rule = re.compile(frame_rule_regex)
    rule_indices = [i for i, line in enumerate(lines) if frame_rule.match(line)]

    if len(rule_indices) < 2:
        raise SendError(
            EXIT_BUSY,
            "No input frame found in visible screen (pane scrolled or unrecognized TUI); refusing send",
            "no_input_frame",
        )

    last_frame_start = rule_indices[-2]
    last_frame_end = rule_indices[-1]
    input_lines = lines[last_frame_start + 1:last_frame_end]

    if not input_lines:
        raise SendError(
            EXIT_BUSY,
            "No input frame found in visible screen (pane scrolled or unrecognized TUI); refusing send",
            "no_input_frame",
        )

    return input_lines


def find_prompt_region(lines: list[str], prompt_regex: str) -> list[str]:
    """Find the last prompt row and every line below it, for TUIs without a framed input box."""
    prompt = re.compile(prompt_regex)
    prompt_indices = [i for i, line in enumerate(lines) if prompt.match(line)]

    if not prompt_indices:
        raise SendError(
            EXIT_BUSY,
            "No input prompt found in visible screen (pane scrolled or unrecognized TUI); refusing send",
            "no_prompt_row",
        )

    return lines[prompt_indices[-1]:]


def check_input_empty(
    runner: HerdrRunner,
    pane_id: str,
    agent_kind: str,
    tui_override: str | None,
) -> None:
    """Check input box is provably empty via visible screen parsing."""
    profile = load_tui_profile(agent_kind, tui_override)
    lines = read_visible_screen(runner, pane_id)
    if "prompt_regex" in profile:
        input_lines = find_prompt_region(lines, profile["prompt_regex"])
    else:
        input_lines = find_input_frame(lines, profile["frame_rule_regex"])

    idle_chrome_patterns = profile["idle_chrome_patterns"]
    chrome_patterns = [re.compile(p) for p in idle_chrome_patterns]

    for line in input_lines:
        is_chrome = any(pat.match(line) for pat in chrome_patterns)
        if not is_chrome and line.strip():
            raise SendError(
                EXIT_BUSY,
                "Input box contains unsubmitted text; refusing send to avoid fusing with operator input",
                "typed_text",
            )
