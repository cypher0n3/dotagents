#!/usr/bin/env python3
"""Fail-closed safe-send gate for herdr agent messaging."""

from __future__ import annotations

import sys

from herdr_lib.cli_parser import setup_arg_parser
from herdr_lib.commands import (
    error_report,
    run_check,
    run_pending_drop,
    run_pending_list,
    run_prompt,
    run_run,
)
from herdr_lib.errors import SendError
from herdr_lib.report import render
from herdr_lib.runner import HerdrRunner

HANDLERS = {
    "check": run_check,
    "prompt": run_prompt,
    "run": run_run,
    "pending list": run_pending_list,
    "pending drop": run_pending_drop,
}


def summary_line(report: dict) -> str:
    """One human-readable line for stderr when a command did not succeed."""
    refusal = report.get("last_refusal") or {}
    detail = (refusal.get("detail") or "").splitlines()
    where = (report.get("target") or {}).get("pane_id") or report.get("pane_id") or ""
    parts = [f"Error: {report.get('result')}"]
    if where:
        parts.append(f"on {where}")
    if refusal:
        parts.append(f"({refusal.get('reason')}): {detail[0] if detail else ''}")
    if report.get("message_id"):
        parts.append(f"; message {report['message_id']} kept")
    return " ".join(parts)


def main() -> int:
    """Parse the command line, run the command, print its report, and return its exit code."""
    args = setup_arg_parser().parse_args()
    command = f"pending {args.pending_command}" if args.command == "pending" else args.command

    try:
        report, code = HANDLERS[command](args, HerdrRunner())
    except SendError as e:
        report, code = error_report(command, e)

    print(render(report, args.yaml))
    if code:
        print(summary_line(report), file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
