"""CLI argument parser for herdr_send.py."""

from __future__ import annotations

import argparse
from pathlib import Path

from .backoff import DEFAULT_PROMPT_WAIT
from .checks import load_profiles


def setup_arg_parser() -> argparse.ArgumentParser:
    """Set up argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="Fail-closed safe-send gate for herdr agent messaging",
        epilog="Run 'herdr_send.py COMMAND --help' for detailed command usage.",
    )
    sub: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command", required=True, help="Command to execute"
    )

    _command(sub, "check", "Run every check and send nothing", target=True, text=False)
    _command(
        sub, "prompt", "Save the message, then send it via herdr agent prompt (pane run for xorc) once the "
        "input box is empty; older saved messages for the target go first", target=True, text=True,
    )
    run = _command(sub, "run", "Send to a shell pane via herdr pane run", target=False, text=True)
    run.add_argument("pane", help="Target pane ID")

    _pending(sub)
    return parser


def _output_flag(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("--yaml", action="store_true", help="Print the report as YAML instead of one JSON line")


def _pending(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Add the pending command group for saved messages."""
    group = sub.add_parser("pending", help="List or drop saved messages", description="List or drop saved messages")
    actions = group.add_subparsers(dest="pending_command", required=True, help="Pending action")

    listing = actions.add_parser("list", help="List waiting and dead messages", description="List waiting and dead "
                                 "messages; expired ones move to dead first")
    listing.add_argument("target", nargs="?", help="Agent name or pane ID (default: every target)")
    _output_flag(listing)

    drop = actions.add_parser("drop", help="Drop waiting messages so they are never sent",
                              description="Drop waiting messages so they are never sent")
    drop.add_argument("message_ids", nargs="*", help="Message IDs to drop")
    drop.add_argument("--target", help="Agent name or pane ID")
    drop.add_argument("--all", action="store_true", help="Drop every waiting message for --target")
    _output_flag(drop)


def _command(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    help_text: str,
    target: bool,
    text: bool,
) -> argparse.ArgumentParser:
    """Add a subcommand with shared options."""
    cmd = sub.add_parser(name, help=help_text, description=help_text)

    tui_choices = list(load_profiles().keys())

    if target:
        cmd.add_argument("target", help="Target agent name or pane ID")
        cmd.add_argument("--expect-kind", help="Require specific agent kind")

    cmd.add_argument("--tui", choices=tui_choices, help="Override TUI profile")

    if target:
        cmd.add_argument(
            "--disable-working",
            action="store_true",
            help="Refuse working state (default allows working and queues message)",
        )

    if text:
        group = cmd.add_mutually_exclusive_group(required=True)
        group.add_argument("--text", help="Message text")
        group.add_argument("--file", type=Path, help="Read message from file")
        group.add_argument("-", dest="stdin", action="store_true", help="Read from stdin")

    if name == "prompt":
        cmd.add_argument("--from-role", help="Sender role for header")
        cmd.add_argument(
            "--reply",
            action=argparse.BooleanOptionalAction,
            help="Whether to expect a reply (default: no)",
        )
        cmd.add_argument(
            "--no-header",
            action="store_true",
            help="Suppress header (for slash commands that must be first)",
        )

    if target:
        default = f"{DEFAULT_PROMPT_WAIT:g} for prompt, 0 for check" if name == "prompt" else "0"
        cmd.add_argument(
            "--wait", type=float,
            help=f"Seconds to keep retrying while the target refuses; 0 is one attempt (default: {default})",
        )
        cmd.add_argument(
            "--interval", type=float, default=2.0,
            help="First retry delay; each later delay doubles, up to 30 s, with +/-20%% jitter (default: 2)",
        )

    cmd.add_argument("--dry-run", action="store_true", help="Run the checks and show what would be sent; "
                     "never sends or saves")
    _output_flag(cmd)

    return cmd
