#!/usr/bin/env python3
"""Tests for herdr_send waits, retries, saved messages, and reports."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from herdr_test_support import EMPTY_SCREEN, TYPED_SCREEN, FakeClock, FakeHerdr

import herdr_send
from herdr_lib import backoff, commands, pending, report
from herdr_lib.errors import SendError
from herdr_lib.exit_codes import (
    EXIT_BLOCKED,
    EXIT_BUSY,
    EXIT_HERDR_ERROR,
    EXIT_INVALID_INPUT,
    EXIT_NOT_IN_HERDR,
    EXIT_SUCCESS,
    EXIT_TARGET_ERROR,
    EXIT_WORKING_REFUSED,
)

ENV = {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p9", "HERDR_SOCKET_PATH": "/run/herdr-test.sock"}


class HerdrSendTestCase(unittest.TestCase):
    """Run commands against a fake herdr, a fake clock, and a private state directory."""

    def setUp(self) -> None:
        self.state = tempfile.mkdtemp(prefix="herdr-send-test-")
        self.addCleanup(shutil.rmtree, self.state, True)
        env = {**ENV, "HERDR_SEND_STATE_DIR": self.state}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.clock = FakeClock()
        clock_patch = mock.patch.object(commands, "time", self.clock)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)

    def run_cmd(self, herdr: FakeHerdr, *argv: str) -> tuple[dict[str, Any], int]:
        """Run one command through its handler; return (report, exit code)."""
        args = herdr_send.setup_arg_parser().parse_args(list(argv))
        name = f"pending {args.pending_command}" if args.command == "pending" else args.command
        try:
            return herdr_send.HANDLERS[name](args, herdr)
        except SendError as e:
            return commands.error_report(name, e)

    def store(self, pane_id: str = "w1:p1") -> pending.PaneStore:
        """Return the saved-message store for a pane."""
        return pending.PaneStore(pane_id)

    def save_old(self, text: str, pane_id: str = "w1:p1", age: float = 60.0, ttl: float = 1800.0) -> str:
        """Save a message as if an earlier caller had left it waiting."""
        created = self.clock.now - age
        message_id = pending.new_message_id(created)
        self.store(pane_id).save({
            "message_id": message_id, "pane_id": pane_id, "target": "coder", "tui": "claude",
            "text": text, "sender_pane": "w1:p7", "created": pending.iso(created),
            "expires": pending.iso(created + ttl), "expires_ts": created + ttl, "attempts": 3,
            "last_refusal": None,
        })
        return message_id


class CheckTest(HerdrSendTestCase):
    """check: every check, optional waiting, never sends or touches saved messages."""

    def test_ready(self) -> None:
        herdr = FakeHerdr()
        result, code = self.run_cmd(herdr, "check", "coder")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["result"], "ready")
        self.assertEqual(result["status_at_return"]["input"], "empty")
        self.assertEqual(result["status_at_return"]["agent_status"], "idle")
        self.assertEqual(herdr.sent, [])

    def test_typed_text_single_attempt_is_refused(self) -> None:
        result, code = self.run_cmd(FakeHerdr(screens=[TYPED_SCREEN]), "check", "coder")
        self.assertEqual(code, EXIT_BUSY)
        self.assertEqual(result["result"], "refused")
        self.assertEqual(result["last_refusal"]["reason"], "typed_text")
        self.assertEqual(result["status_at_return"]["input"], "typed_text")
        self.assertEqual(self.clock.sleeps, [])

    def test_wait_until_text_is_cleared(self) -> None:
        herdr = FakeHerdr(screens=[TYPED_SCREEN, TYPED_SCREEN, EMPTY_SCREEN])
        result, code = self.run_cmd(herdr, "check", "coder", "--wait", "60")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["last_refusal"]["reason"], "typed_text")
        self.assertEqual(len(self.clock.sleeps), 2)

    def test_wait_timeout_reports_real_status(self) -> None:
        result, code = self.run_cmd(FakeHerdr(screens=[TYPED_SCREEN]), "check", "coder", "--wait", "20")
        self.assertEqual(code, EXIT_BUSY)
        self.assertEqual(result["result"], "timeout")
        self.assertGreater(result["attempts"], 2)
        self.assertAlmostEqual(sum(self.clock.sleeps), 20.0, places=3)
        self.assertEqual(result["status_at_return"]["input"], "typed_text")
        self.assertIn("never clear or submit", result["next_step"])

    def test_herdr_error_fails_fast(self) -> None:
        herdr = FakeHerdr()
        herdr.get_error = "connection refused"
        result, code = self.run_cmd(herdr, "check", "coder", "--wait", "60")
        self.assertEqual(code, EXIT_HERDR_ERROR)
        self.assertEqual(result["result"], "error")
        self.assertEqual(result["attempts"], 1)

    def test_shows_saved_messages_without_changing_them(self) -> None:
        old = self.save_old("older")
        result, _ = self.run_cmd(FakeHerdr(), "check", "coder")
        self.assertEqual([m["message_id"] for m in result["pending_for_target"]], [old])
        self.assertEqual([r["message_id"] for r in self.store().waiting()], [old])

    def test_unknown_target(self) -> None:
        result, code = self.run_cmd(FakeHerdr(), "check", "ghost")
        self.assertEqual(code, EXIT_TARGET_ERROR)
        self.assertEqual(result["last_refusal"]["reason"], "target_error")


class PromptTest(HerdrSendTestCase):
    """prompt: save, wait with backoff, deliver oldest first, report."""

    def test_sends_and_clears_saved_copy(self) -> None:
        herdr = FakeHerdr()
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "hello", "--from-role", "tester")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["result"], "sent")
        self.assertEqual(result["delivered_by"], "w1:p9")
        self.assertEqual(herdr.sent[0][:3], ["agent", "prompt", "w1:p1"])
        self.assertIn("hello", herdr.sent[0][3])
        self.assertEqual(result["pending_for_target"], 0)
        self.assertEqual(self.store().waiting(), [])
        self.assertFalse(list(Path(self.state).rglob("sent/*.json")))
        self.assertEqual(result["status_at_return"]["input"], "submitted")

    def test_xorc_uses_pane_run(self) -> None:
        herdr = FakeHerdr(agents=[{"pane_id": "w1:p1", "agent": "xorc"}])
        _, code = self.run_cmd(herdr, "prompt", "w1:p1", "--tui", "xorc", "--text", "build", "--no-header")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(herdr.sent, [["pane", "run", "w1:p1", "build"]])

    def test_waits_while_someone_types_then_sends(self) -> None:
        herdr = FakeHerdr(screens=[TYPED_SCREEN, TYPED_SCREEN, TYPED_SCREEN, EMPTY_SCREEN])
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "hi", "--no-header")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["attempts"], 4)
        self.assertEqual(len(herdr.sent), 1)
        first, second, third = self.clock.sleeps
        self.assertTrue(1.6 <= first <= 2.4 and 3.2 <= second <= 4.8 and 6.4 <= third <= 9.6)

    def test_sends_right_after_one_empty_read(self) -> None:
        herdr = FakeHerdr()
        self.run_cmd(herdr, "prompt", "coder", "--text", "hi", "--no-header")
        reads = [i for i, c in enumerate(herdr.calls) if c[:2] == ["pane", "read"]]
        sends = [i for i, c in enumerate(herdr.calls) if c[:2] == ["agent", "prompt"]]
        self.assertEqual(len(reads), 1)
        self.assertEqual(sends[0] - reads[0], 2)  # only the state re-check sits between them

    def test_timeout_keeps_message_with_reason(self) -> None:
        herdr = FakeHerdr(screens=[TYPED_SCREEN])
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "hi", "--wait", "40", "--no-header")
        self.assertEqual(code, EXIT_BUSY)
        self.assertEqual(result["result"], "timeout")
        self.assertEqual(herdr.sent, [])
        saved = self.store().waiting()
        self.assertEqual([r["message_id"] for r in saved], [result["message_id"]])
        self.assertEqual(saved[0]["last_refusal"]["reason"], "typed_text")
        self.assertEqual(saved[0]["attempts"], result["attempts"])
        self.assertIn(f"pending drop {result['message_id']}", result["next_step"])

    def test_default_wait_is_180_seconds(self) -> None:
        result, _ = self.run_cmd(FakeHerdr(screens=[TYPED_SCREEN]), "prompt", "coder", "--text", "x", "--no-header")
        self.assertAlmostEqual(sum(self.clock.sleeps), 180.0, places=3)
        self.assertLessEqual(max(self.clock.sleeps), backoff.MAX_DELAY * 1.2 + 1e-9)
        self.assertEqual(result["result"], "timeout")

    def test_wait_zero_is_one_attempt(self) -> None:
        result, code = self.run_cmd(FakeHerdr(screens=[TYPED_SCREEN]), "prompt", "coder", "--text", "x",
                                    "--wait", "0", "--no-header")
        self.assertEqual(code, EXIT_BUSY)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["result"], "timeout")

    def test_blocked_dialog_is_waited_out(self) -> None:
        herdr = FakeHerdr(statuses=["blocked", "idle"])
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--no-header")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["last_refusal"]["code"], EXIT_BLOCKED)

    def test_working_target_gets_message_by_default(self) -> None:
        herdr = FakeHerdr(statuses=["working"])
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--no-header")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["attempts"], 1)

    def test_disable_working_waits_for_idle(self) -> None:
        herdr = FakeHerdr(statuses=["working", "working", "idle"])
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--no-header", "--disable-working")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["last_refusal"]["code"], EXIT_WORKING_REFUSED)
        self.assertEqual(result["attempts"], 3)

    def test_older_saved_messages_go_first(self) -> None:
        old = self.save_old("older message")
        herdr = FakeHerdr()
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "newer", "--no-header")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual([argv[3] for argv in herdr.sent], ["older message", "newer"])
        self.assertEqual(result["delivered_first"], [old])
        self.assertEqual(self.clock.sleeps, [])  # a send is followed by an immediate recheck

    def test_message_delivered_by_another_caller(self) -> None:
        herdr = FakeHerdr(screens=[TYPED_SCREEN])
        store = self.store()

        def other_caller_delivers(_seconds: float) -> None:
            for record in store.waiting():
                store.claim(record["message_id"], "w1:p5")
                store.mark_sent(record["message_id"], "w1:p5")

        with mock.patch.object(self.clock, "sleep", side_effect=other_caller_delivers):
            result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--no-header")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["delivered_by"], "w1:p5")
        self.assertEqual(herdr.sent, [])

    def test_expired_message_is_never_sent_and_reported_once(self) -> None:
        old = self.save_old("stale", age=3600.0, ttl=1800.0)
        herdr = FakeHerdr()
        first, _ = self.run_cmd(herdr, "prompt", "coder", "--text", "fresh", "--no-header")
        self.assertEqual([argv[3] for argv in herdr.sent], ["fresh"])
        self.assertEqual([d["message_id"] for d in first["dead_reported"]], [old])
        self.assertEqual(first["dead_reported"][0]["dead_reason"], "expired")
        second, _ = self.run_cmd(herdr, "prompt", "coder", "--text", "again", "--no-header")
        self.assertEqual(second["dead_reported"], [])

    def test_long_wait_extends_expiry(self) -> None:
        herdr = FakeHerdr(screens=[TYPED_SCREEN])
        result, _ = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--wait", "1", "--no-header")
        saved = self.store().waiting()[0]
        self.assertAlmostEqual(saved["expires_ts"] - (self.clock.now - result["waited_s"]), 1800.0, delta=2)

    def test_send_failure_keeps_message_waiting(self) -> None:
        herdr = FakeHerdr()
        herdr.send_error = "socket closed"
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--no-header")
        self.assertEqual(code, EXIT_HERDR_ERROR)
        self.assertEqual(result["result"], "error")
        saved = self.store().waiting()
        self.assertEqual(saved[0]["last_refusal"]["reason"], "herdr_error")

    def test_dry_run_saves_and_sends_nothing(self) -> None:
        herdr = FakeHerdr()
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--no-header", "--dry-run")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["result"], "dry_run")
        self.assertEqual(result["argv"], ["herdr", "agent", "prompt", "w1:p1", "x"])
        self.assertEqual(herdr.sent, [])
        self.assertEqual(self.store().waiting(), [])

    def test_gone_pane_kills_its_saved_messages(self) -> None:
        old = self.save_old("for a closed pane", pane_id="w1:p3")
        result, code = self.run_cmd(FakeHerdr(), "prompt", "w1:p3", "--text", "x", "--no-header")
        self.assertEqual(code, EXIT_TARGET_ERROR)
        self.assertEqual(result["result"], "error")
        self.assertEqual(self.store("w1:p3").dead(old)["dead_reason"], "target_gone")

    def test_missing_profile_fails_before_saving(self) -> None:
        herdr = FakeHerdr(agents=[{"pane_id": "w1:p1", "name": "coder", "agent": "mystery"}])
        result, code = self.run_cmd(herdr, "prompt", "coder", "--text", "x", "--no-header")
        self.assertEqual(code, EXIT_BUSY)
        self.assertEqual(result["last_refusal"]["reason"], "no_profile")
        self.assertEqual(self.store().waiting(), [])

    def test_reads_file_and_stdin(self) -> None:
        path = Path(self.state) / "msg.txt"
        path.write_text("from file\n", encoding="utf-8")
        herdr = FakeHerdr()
        self.run_cmd(herdr, "prompt", "coder", "--file", str(path), "--no-header")
        with mock.patch("sys.stdin", io.StringIO("from stdin\n")):
            self.run_cmd(herdr, "prompt", "coder", "-", "--no-header")
        self.assertEqual([argv[3] for argv in herdr.sent], ["from file", "from stdin"])

    def test_saved_files_are_private(self) -> None:
        self.run_cmd(FakeHerdr(screens=[TYPED_SCREEN]), "prompt", "coder", "--text", "x", "--wait", "0",
                     "--no-header")
        saved = next(Path(self.state).rglob("*.json"))
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertEqual(saved.parent.stat().st_mode & 0o777, 0o700)


class StoreTest(HerdrSendTestCase):
    """Saved-message store edge cases."""

    def test_claim_is_exclusive(self) -> None:
        message_id = self.save_old("x")
        store = self.store()
        self.assertIsNotNone(store.claim(message_id, "w1:p5"))
        self.assertIsNone(store.claim(message_id, "w1:p6"))

    def test_stuck_claim_is_never_resent(self) -> None:
        message_id = self.save_old("x")
        store = self.store()
        store.claim(message_id, "w1:p5")
        sending = next(Path(self.state).rglob("*.sending"))
        os.utime(sending, (self.clock.now - 120, self.clock.now - 120))
        store.sweep(self.clock.now)
        self.assertEqual(store.dead(message_id)["dead_reason"], "interrupted_during_send")

    def test_old_records_are_pruned(self) -> None:
        message_id = self.save_old("x")
        store = self.store()
        store.kill(message_id, "dropped")
        dead = next(Path(self.state).rglob("dead/*.json"))
        os.utime(dead, (self.clock.now - pending.DEAD_KEEP - 1,) * 2)
        store.sweep(self.clock.now)
        self.assertIsNone(store.dead(message_id))

    def test_server_key_defaults_without_socket(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(pending.server_key(), "default")
            self.assertTrue(str(pending.state_root()).endswith("herdr-send"))


class PendingCommandTest(HerdrSendTestCase):
    """pending list and pending drop."""

    def test_list_and_drop_by_id(self) -> None:
        message_id = self.save_old("x")
        listed, code = self.run_cmd(FakeHerdr(), "pending", "list")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(listed["panes"][0]["pane_id"], "w1:p1")
        self.assertEqual(listed["panes"][0]["waiting"][0]["message_id"], message_id)
        dropped, code = self.run_cmd(FakeHerdr(), "pending", "drop", message_id)
        self.assertEqual((code, dropped["dropped"]), (EXIT_SUCCESS, [message_id]))
        self.assertEqual(self.store().dead(message_id)["dead_reason"], "dropped")

    def test_list_by_name_and_pane(self) -> None:
        self.save_old("x")
        by_name, _ = self.run_cmd(FakeHerdr(), "pending", "list", "coder")
        by_pane, _ = self.run_cmd(FakeHerdr(), "pending", "list", "w1:p1")
        self.assertEqual(by_name["panes"], by_pane["panes"])

    def test_drop_all_for_target(self) -> None:
        self.save_old("a", age=90)
        self.save_old("b", age=60)
        result, code = self.run_cmd(FakeHerdr(), "pending", "drop", "--target", "w1:p1", "--all")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(len(result["dropped"]), 2)
        self.assertEqual(self.store().waiting(), [])

    def test_drop_unknown_id(self) -> None:
        result, code = self.run_cmd(FakeHerdr(), "pending", "drop", "nope")
        self.assertEqual(code, EXIT_TARGET_ERROR)
        self.assertEqual(result["not_found"], ["nope"])

    def test_drop_needs_ids_or_all_with_target(self) -> None:
        _, code = self.run_cmd(FakeHerdr(), "pending", "drop", "--all")
        self.assertEqual(code, EXIT_INVALID_INPUT)
        _, code = self.run_cmd(FakeHerdr(), "pending", "drop")
        self.assertEqual(code, EXIT_INVALID_INPUT)


class RunTest(HerdrSendTestCase):
    """run: shell panes only."""

    def test_sends_to_shell_pane(self) -> None:
        herdr = FakeHerdr()
        result, code = self.run_cmd(herdr, "run", "w1:p4", "--text", "just test")
        self.assertEqual((code, result["result"]), (EXIT_SUCCESS, "sent"))
        self.assertEqual(herdr.sent, [["pane", "run", "w1:p4", "just test"]])

    def test_refuses_agent_pane(self) -> None:
        result, code = self.run_cmd(FakeHerdr(), "run", "w1:p1", "--text", "x")
        self.assertEqual(code, EXIT_TARGET_ERROR)
        self.assertIn("owned by an agent", result["last_refusal"]["detail"])

    def test_dry_run(self) -> None:
        herdr = FakeHerdr()
        result, _ = self.run_cmd(herdr, "run", "w1:p4", "--text", "x", "--dry-run")
        self.assertEqual(result["result"], "dry_run")
        self.assertEqual(herdr.sent, [])


class OutputTest(HerdrSendTestCase):
    """main prints one JSON line by default, YAML with --yaml, and a stderr summary on failure."""

    def main(self, herdr: FakeHerdr, *argv: str) -> tuple[int, str, str]:
        """Run herdr_send.main against the fake herdr."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["herdr_send.py", *argv]), \
                mock.patch.object(herdr_send, "HerdrRunner", return_value=herdr), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = herdr_send.main()
        return code, out.getvalue(), err.getvalue()

    def test_json_is_one_line(self) -> None:
        code, out, err = self.main(FakeHerdr(), "check", "coder")
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(out.count("\n"), 1)
        self.assertEqual(json.loads(out)["result"], "ready")
        self.assertEqual(err, "")

    def test_yaml(self) -> None:
        _, out, _ = self.main(FakeHerdr(), "check", "coder", "--yaml")
        self.assertIn("result: ready\n", out)
        self.assertIn("target:\n  requested: coder\n", out)

    def test_failure_summary_on_stderr(self) -> None:
        code, out, err = self.main(FakeHerdr(screens=[TYPED_SCREEN]), "prompt", "coder", "--text", "x",
                                   "--wait", "5", "--no-header")
        self.assertEqual(code, EXIT_BUSY)
        self.assertEqual(json.loads(out)["result"], "timeout")
        self.assertIn("Error: timeout on w1:p1 (typed_text)", err)
        self.assertIn("kept", err)

    def test_not_in_herdr(self) -> None:
        with mock.patch.dict(os.environ, {"HERDR_ENV": "0"}):
            code, out, err = self.main(FakeHerdr(), "check", "coder")
        self.assertEqual(code, EXIT_NOT_IN_HERDR)
        self.assertEqual(json.loads(out)["last_refusal"]["reason"], "not_in_herdr")
        self.assertIn("Not running inside Herdr", err)


class FormatTest(unittest.TestCase):
    """Backoff and YAML rendering."""

    def test_delays_double_to_the_cap_with_jitter(self) -> None:
        gen = backoff.delays(2.0)
        values = [next(gen) for _ in range(8)]
        for value, base in zip(values, [2, 4, 8, 16, 30, 30, 30, 30]):
            self.assertTrue(base * 0.8 <= value <= base * 1.2, (value, base))

    def test_zero_interval_never_sleeps(self) -> None:
        gen = backoff.delays(0.0)
        self.assertEqual([next(gen) for _ in range(3)], [0.0, 0.0, 0.0])

    def test_yaml_quotes_ambiguous_strings(self) -> None:
        text = report.to_yaml({"a": "true", "b": "x: y", "c": None, "d": [], "e": [{"k": 1}], "f": {}})
        self.assertEqual(text, 'a: "true"\nb: "x: y"\nc: null\nd: []\ne:\n  - k: 1\nf: {}')


if __name__ == "__main__":
    unittest.main()
