"""Command implementations for herdr_send.py.

Every command returns (report, exit_code). The report is one structured document that says
what happened, why, and the target's real status when the command returned.
"""

from __future__ import annotations

import os
import re
import sys
import time
from argparse import Namespace
from typing import Any, Callable

from . import pending
from .backoff import DEFAULT_PROMPT_WAIT, delays
from .checks import (
    check_herdr_env,
    check_input_empty,
    check_not_blocked,
    check_state_allowed,
    get_agent_snapshot,
    list_agents,
    load_tui_profile,
    resolve_target,
    verify_state_unchanged,
)
from .errors import SendError
from .exit_codes import (
    EXIT_BUSY,
    EXIT_HERDR_ERROR,
    EXIT_INVALID_INPUT,
    EXIT_NOT_IN_HERDR,
    EXIT_SUCCESS,
    EXIT_TARGET_ERROR,
)
from .message import format_message, validate_message
from .runner import HerdrRunner

Report = dict[str, Any]

# Waiting cannot fix these, so they fail on the first pass.
HARD_EXIT_CODES = {EXIT_TARGET_ERROR, EXIT_NOT_IN_HERDR, EXIT_HERDR_ERROR, EXIT_INVALID_INPUT}
FAIL_FAST_REASONS = {"no_profile"}
# Internal: a send just happened, so check again at once instead of backing off.
RECHECK = "recheck"
PANE_ID = re.compile(r"^w[0-9A-Za-z]+:p[0-9A-Za-z]+$")

NEXT_STEPS = {
    "typed_text": "Someone has unsubmitted text in the input box; never clear or submit it. Retry later.",
    "blocked": "A dialog is open; answer it only with the user's approval, then retry.",
    "working": "The target is still working and --disable-working is set; retry later or drop the flag.",
    "state_changed": "The target changed state during the checks; retry.",
    "claimed_elsewhere": "Another caller is sending this message now; check pending list for the result.",
    "no_input_frame": "No input box is visible (loading, scrolled, or a dialog); check the pane, then retry.",
    "no_prompt_row": "No prompt row is visible (loading, scrolled, or a dialog); check the pane, then retry.",
    "not_interactive_ready": "herdr says the target is not ready for input; retry later.",
    "unknown_state": "herdr cannot classify the target's state; read the pane before retrying.",
    "missing_field": "herdr returned incomplete agent data; check the herdr version.",
    "no_profile": "No TUI profile matches this target; pass --tui or add a profile.",
    "target_error": "Check the target name or pane ID with herdr agent list.",
    "not_in_herdr": "Run inside a herdr pane (HERDR_ENV=1).",
    "herdr_error": "herdr failed; check that the herdr server is running, then retry.",
    "invalid_input": "Fix the message text and send again.",
}


class WaitTimeout(Exception):
    """The wait ran out while the target kept refusing."""

    def __init__(self, last: SendError):
        super().__init__(last.message)
        self.last = last


class Waiter:
    """Retry one readiness check with escalating delays until it passes or the deadline passes."""

    def __init__(self, wait: float, interval: float, on_refusal: Callable[[SendError, int], None] | None = None):
        self.start = time.time()
        self.deadline = self.start + max(wait, 0.0)
        self.delays = delays(interval)
        self.attempts = 0
        self.last: SendError | None = None
        self.on_refusal = on_refusal

    def waited(self) -> float:
        """Seconds since the wait started."""
        return round(time.time() - self.start, 1)

    def until_ready(self, attempt: Callable[[], None]) -> None:
        """Run attempt until it passes; raise the hard error or WaitTimeout."""
        while True:
            self.attempts += 1
            try:
                attempt()
                return
            except SendError as e:
                if e.exit_code in HARD_EXIT_CODES or e.reason in FAIL_FAST_REASONS:
                    raise
                if e.reason == RECHECK:
                    continue
                self.last = e
                if self.on_refusal:
                    self.on_refusal(e, self.attempts)
                remaining = self.deadline - time.time()
                if remaining <= 0:
                    raise WaitTimeout(e) from e
                time.sleep(min(next(self.delays), remaining))


class Target:
    """A resolved target and the latest observation of it."""

    def __init__(self, runner: HerdrRunner, args: Namespace, pane_id: str, agent_kind: str):
        self.runner = runner
        self.requested = args.target
        self.pane_id = pane_id
        self.agent_kind = agent_kind
        self.tui_override = args.tui
        self.tui = args.tui or agent_kind
        self.disable_working = args.disable_working
        self.observed: dict[str, Any] = {"input": "unchecked"}

    def describe(self) -> dict[str, Any]:
        """Return the target block of a report."""
        return {"requested": self.requested, "pane_id": self.pane_id, "tui": self.tui}

    def _snapshot(self) -> dict[str, Any]:
        agent = get_agent_snapshot(self.runner, self.pane_id)
        self.observed.update(
            agent_status=agent.get("agent_status"),
            interactive_ready=agent.get("interactive_ready"),
            seq=agent.get("state_change_seq"),
            observed_at=pending.iso(time.time()),
        )
        return agent

    def check_ready(self) -> None:
        """Run every check once."""
        self.observed = {"input": "unchecked"}
        agent = self._snapshot()
        check_not_blocked(agent, self.runner, self.pane_id)
        check_state_allowed(agent, self.disable_working)
        try:
            check_input_empty(self.runner, self.pane_id, self.agent_kind, self.tui_override)
        except SendError as e:
            self.observed["input"] = e.reason
            raise
        self.observed["input"] = "empty"
        verify_state_unchanged(get_agent_snapshot(self.runner, self.pane_id), agent["state_change_seq"])

    def refresh(self) -> None:
        """Re-read the agent state after a send, so the report shows status at return."""
        try:
            self._snapshot()
            self.observed["input"] = "submitted"
        except SendError as e:
            self.observed["refresh_error"] = e.message

    def send_argv(self, text: str, tui: str | None = None) -> list[str]:
        """Return the herdr argv that delivers text (xorc has no agent kind, so it uses pane run)."""
        if (tui or self.tui) == "xorc":
            return ["pane", "run", self.pane_id, text]
        return ["agent", "prompt", self.pane_id, text]


def read_message_text(args: Namespace) -> str:
    """Read message text from --text, --file, or stdin."""
    if args.text is not None:
        return args.text

    if args.file:
        try:
            return args.file.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise SendError(EXIT_INVALID_INPUT, f"Failed to read file: {e}") from e

    return sys.stdin.read().strip()


def refusal_block(error: SendError | None) -> dict[str, Any] | None:
    """Return the last_refusal block of a report."""
    if error is None:
        return None
    return {"code": error.exit_code, "reason": error.reason, "detail": error.message}


def next_step(reason: str | None, message_id: str | None = None) -> str:
    """Say what the caller should do next."""
    step = NEXT_STEPS.get(reason or "", "Read the target pane before retrying.")
    if message_id:
        step += (
            f" Message {message_id} stays saved; the next herdr_send.py prompt to this target delivers it first,"
            f" or remove it with: herdr_send.py pending drop {message_id}"
        )
    return step


def error_report(command: str, error: SendError) -> tuple[Report, int]:
    """Build a report for a failure before any target was resolved."""
    report = {
        "command": command,
        "result": "error",
        "exit_code": error.exit_code,
        "last_refusal": refusal_block(error),
        "next_step": next_step(error.reason),
    }
    return report, error.exit_code


def _resolve(runner: HerdrRunner, args: Namespace) -> Target:
    own_pane = os.environ.get("HERDR_PANE_ID")
    try:
        pane_id, _, agent_kind = resolve_target(runner, args.target, args.expect_kind, own_pane)
    except SendError as e:
        if e.reason == "target_error" and PANE_ID.match(args.target or ""):
            store = pending.PaneStore(args.target)
            for record in store.waiting():
                store.kill(record["message_id"], "target_gone")
        raise
    load_tui_profile(agent_kind, args.tui)
    return Target(runner, args, pane_id, agent_kind)


def _base_report(command: str, target: Target, waiter: Waiter) -> Report:
    return {
        "command": command,
        "result": None,
        "exit_code": EXIT_SUCCESS,
        "target": target.describe(),
        "waited_s": waiter.waited(),
        "attempts": waiter.attempts,
        "last_refusal": refusal_block(waiter.last),
        "status_at_return": target.observed,
    }


def _apply_failure(report: Report, error: SendError, timed_out: bool, message_id: str | None) -> int:
    if error.exit_code in HARD_EXIT_CODES:
        result = "error"
    else:
        result = "timeout" if timed_out else "refused"
    report.update(
        result=result,
        exit_code=error.exit_code,
        last_refusal=refusal_block(error),
        next_step=next_step(error.reason, message_id),
    )
    return error.exit_code


def _wait_checks(args: Namespace, target: Target) -> tuple[Waiter, SendError | None, bool]:
    """Wait for the target to pass every check, without sending."""
    waiter = Waiter(args.wait or 0.0, args.interval)
    try:
        waiter.until_ready(target.check_ready)
    except WaitTimeout as e:
        return waiter, e.last, bool(args.wait)
    except SendError as e:
        return waiter, e, False
    return waiter, None, False


def _saved_view(pane_id: str) -> dict[str, Any]:
    """Saved and dead messages for a target, read without changing anything."""
    store = pending.PaneStore(pane_id)
    return {
        "pending_for_target": [pending.summarize(r) for r in store.waiting()],
        "dead_for_target": store.all_dead(),
    }


def run_check(args: Namespace, runner: HerdrRunner) -> tuple[Report, int]:
    """Run every check, retrying until ready or the wait runs out; never send or change saved messages."""
    check_herdr_env()
    target = _resolve(runner, args)
    waiter, error, timed_out = _wait_checks(args, target)
    report = _base_report("check", target, waiter)
    report.update(_saved_view(target.pane_id))
    if error is not None:
        return report, _apply_failure(report, error, timed_out, None)
    report.update(result="ready", next_step="The target is ready; nothing was sent.")
    return report, EXIT_SUCCESS


class Delivery:
    """Deliver a target's saved messages oldest first, ending with this caller's own."""

    def __init__(self, target: Target, store: pending.PaneStore, own_id: str):
        self.target = target
        self.store = store
        self.own_id = own_id
        self.sender = os.environ.get("HERDR_PANE_ID")
        self.delivered_first: list[str] = []
        self.outcome: dict[str, Any] | None = None

    def _settled_elsewhere(self) -> dict[str, Any] | None:
        """Return the final state of this caller's message if another sender settled it."""
        if any(r["message_id"] == self.own_id for r in self.store.waiting()):
            return None
        sent = self.store.take_sent(self.own_id)
        if sent is not None:
            return {"result": "sent", "delivered_by": sent.get("delivered_by")}
        dead = self.store.dead(self.own_id)
        if dead is not None:
            return {"result": "dead", "dead_reason": dead.get("dead_reason")}
        return None

    def attempt(self) -> None:
        """Check the target, then send the oldest waiting message; succeed once this caller's is sent."""
        self.outcome = self._settled_elsewhere()
        if self.outcome is not None:
            return
        self.target.check_ready()
        waiting = self.store.waiting()
        if not waiting:
            raise SendError(EXIT_BUSY, "Another caller is sending this message now", "claimed_elsewhere")
        record = self.store.claim(waiting[0]["message_id"], self.sender)
        if record is None:
            raise SendError(EXIT_BUSY, "Another caller claimed the next message first", RECHECK)
        try:
            self.target.runner.send(self.target.send_argv(record["text"], record.get("tui")))
        except SendError as e:
            self.store.release(record["message_id"], last_refusal=refusal_block(e))
            raise
        self.store.mark_sent(record["message_id"], self.sender)
        if record["message_id"] != self.own_id:
            self.delivered_first.append(record["message_id"])
            raise SendError(EXIT_BUSY, "Delivered an older saved message first", RECHECK)
        self.store.take_sent(self.own_id)
        self.outcome = {"result": "sent", "delivered_by": self.sender}

    def note_refusal(self, error: SendError, attempts: int) -> None:
        """Record the latest refusal on the saved message."""
        self.store.update(
            self.own_id,
            attempts=attempts,
            last_refusal=refusal_block(error),
            status_at_refusal=dict(self.target.observed),
        )


def _new_record(target: Target, text: str, wait: float) -> dict[str, Any]:
    now = time.time()
    expires = now + max(pending.MIN_TTL, wait)
    return {
        "message_id": pending.new_message_id(now),
        "pane_id": target.pane_id,
        "target": target.requested,
        "tui": target.tui,
        "text": text,
        "sender_pane": os.environ.get("HERDR_PANE_ID"),
        "created": pending.iso(now),
        "expires": pending.iso(expires),
        "expires_ts": expires,
        "attempts": 0,
        "last_refusal": None,
    }


def _dry_run(args: Namespace, target: Target, text: str) -> tuple[Report, int]:
    waiter, error, timed_out = _wait_checks(args, target)
    report = _base_report("prompt", target, waiter)
    report.update(dry_run=True, text=text, argv=["herdr", *target.send_argv(text)], **_saved_view(target.pane_id))
    if error is not None:
        return report, _apply_failure(report, error, timed_out, None)
    report.update(result="dry_run", next_step="Dry run: nothing was sent or saved.")
    return report, EXIT_SUCCESS


def run_prompt(args: Namespace, runner: HerdrRunner) -> tuple[Report, int]:
    """Save the message, then deliver this target's saved messages oldest first, retrying until sent."""
    check_herdr_env()
    validated = validate_message(read_message_text(args))
    target = _resolve(runner, args)
    own_pane = os.environ.get("HERDR_PANE_ID")
    text = format_message(validated, args.from_role, own_pane, bool(args.reply), args.no_header)
    if args.dry_run:
        return _dry_run(args, target, text)

    wait = DEFAULT_PROMPT_WAIT if args.wait is None else args.wait
    store = pending.PaneStore(target.pane_id)
    store.sweep(time.time())
    record = _new_record(target, text, wait)
    store.save(record)
    delivery = Delivery(target, store, record["message_id"])
    waiter = Waiter(wait, args.interval, delivery.note_refusal)
    error, timed_out = None, False
    try:
        waiter.until_ready(delivery.attempt)
    except WaitTimeout as e:
        error, timed_out = e.last, True
    except SendError as e:
        error = e
    return _prompt_report(
        target=target, waiter=waiter, store=store, delivery=delivery, error=error, timed_out=timed_out
    )


def _prompt_report(
    *,
    target: Target,
    waiter: Waiter,
    store: pending.PaneStore,
    delivery: Delivery,
    error: SendError | None,
    timed_out: bool,
) -> tuple[Report, int]:
    outcome = delivery.outcome or {}
    if outcome.get("result") == "sent":
        target.refresh()
    report = _base_report("prompt", target, waiter)
    report.update(
        message_id=delivery.own_id,
        delivered_first=delivery.delivered_first,
        delivered_by=outcome.get("delivered_by"),
    )
    if error is not None:
        code = _apply_failure(report, error, timed_out, delivery.own_id)
    elif outcome.get("result") == "sent":
        code = EXIT_SUCCESS
        report.update(result="sent", next_step="Delivered.")
    else:
        code = EXIT_TARGET_ERROR
        report.update(
            result="error",
            exit_code=code,
            next_step=f"Message was not sent ({outcome.get('dead_reason')}); send it again if it is still needed.",
        )
    report.update(pending_for_target=len(store.waiting()), dead_reported=store.unreported_dead())
    return report, code


def run_run(args: Namespace, runner: HerdrRunner) -> tuple[Report, int]:
    """Send a command line to a shell pane via herdr pane run."""
    check_herdr_env()
    validated = validate_message(read_message_text(args))
    pane_id = args.pane

    for agent in list_agents(runner):
        if agent.get("pane_id") == pane_id:
            raise SendError(
                EXIT_TARGET_ERROR,
                f"Pane {pane_id} is owned by an agent; use 'prompt' command instead of 'run'",
            )

    argv = ["pane", "run", pane_id, validated]
    report: Report = {"command": "run", "pane_id": pane_id, "exit_code": EXIT_SUCCESS}
    if args.dry_run:
        report.update(result="dry_run", text=validated, argv=["herdr", *argv], next_step="Dry run: nothing was sent.")
        return report, EXIT_SUCCESS

    runner.send(argv)
    report.update(result="sent", next_step="Delivered.")
    return report, EXIT_SUCCESS


def _stores_for(runner: HerdrRunner, target: str | None) -> list[pending.PaneStore]:
    if not target:
        return pending.all_pane_stores()
    if PANE_ID.match(target):
        return [pending.PaneStore(target)]
    check_herdr_env()
    pane_id, _, _ = resolve_target(runner, target, None, os.environ.get("HERDR_PANE_ID"))
    return [pending.PaneStore(pane_id)]


def run_pending_list(args: Namespace, runner: HerdrRunner) -> tuple[Report, int]:
    """List saved and dead messages, expiring any that are past their time."""
    panes = []
    for store in _stores_for(runner, args.target):
        store.sweep(time.time())
        panes.append({
            "pane_id": store.pane_id,
            "waiting": [pending.summarize(r) for r in store.waiting()],
            "dead": store.all_dead(),
        })
    report = {"command": "pending list", "result": "listed", "exit_code": EXIT_SUCCESS, "panes": panes}
    return report, EXIT_SUCCESS


def run_pending_drop(args: Namespace, runner: HerdrRunner) -> tuple[Report, int]:
    """Drop saved messages by ID, or every waiting message for one target with --all."""
    if args.all and not args.target:
        raise SendError(EXIT_INVALID_INPUT, "--all needs --target")
    if not args.all and not args.message_ids:
        raise SendError(EXIT_INVALID_INPUT, "Name message IDs to drop, or pass --target with --all")
    dropped, missing = [], list(args.message_ids)
    for store in _stores_for(runner, args.target):
        for record in store.waiting():
            message_id = record["message_id"]
            if args.all or message_id in missing:
                store.kill(message_id, "dropped")
                dropped.append(message_id)
                if message_id in missing:
                    missing.remove(message_id)
    code = EXIT_TARGET_ERROR if missing else EXIT_SUCCESS
    report = {
        "command": "pending drop",
        "result": "error" if missing else "dropped",
        "exit_code": code,
        "dropped": dropped,
        "not_found": missing,
        "next_step": (
            "Some IDs were not waiting; see herdr_send.py pending list." if missing
            else "Dropped messages are in dead/ and will never be sent."
        ),
    }
    return report, code
