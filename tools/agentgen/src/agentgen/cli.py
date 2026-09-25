"""Command-line entry point: ``agentgen generate [--check] [--accept-source]``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentgen import GENERATOR, manifest, publish
from agentgen.errors import GenerationError
from agentgen.render import render_all
from agentgen.sources import SOURCES_DIR, load_sources

HAND_EDIT_HINT = (
    "Move the change into agent_sources/ (a role in roles/, its body in prompts/, or a target profile) "
    "and restore the file, or discard it with `just generate-agents-accept-source` (agentgen --accept-source). "
    "If `just lint-md` rewrote a generated Markdown file, fix the source so it renders lint clean."
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentgen", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="render agent_sources/ into agents/ and generated/")
    generate.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    mode = generate.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report stale, missing, or obsolete outputs and write nothing")
    mode.add_argument("--accept-source", action="store_true",
                      help="overwrite managed files that were edited by hand, such as after a merge conflict")
    return parser


def _report(prefix: str, items: list[str], stream=None) -> None:
    for item in items:
        print(f"  {prefix}: {item}", file=stream or sys.stdout)


def generate(root: Path, *, check: bool, accept_source: bool) -> int:
    root = root.resolve()
    if not (root / SOURCES_DIR).is_dir():
        print(f"agentgen: {root} has no {SOURCES_DIR}/ directory", file=sys.stderr)
        return 2
    sources = load_sources(root)
    rendered = render_all(root, sources.profiles, sources.roles)
    outputs = {item.path: item.content for item in rendered}
    manifest_bytes = manifest.build(root, sources, rendered)
    if accept_source:
        # A conflicted or damaged manifest is exactly what --accept-source recovers from.
        try:
            recorded = manifest.recorded_outputs(root)
        except GenerationError:
            recorded = None
    else:
        recorded = manifest.recorded_outputs(root)
    result = publish.plan(root, outputs, manifest_bytes, recorded, accept_source=accept_source)

    if check:
        stale = result.create + result.update + [item.split(":", 1)[0] for item in result.conflicts]
        if not stale and not result.remove and not result.manifest_changed:
            print(f"agentgen: {len(outputs)} outputs and {manifest.MANIFEST_PATH} are current")
            return 0
        print("agentgen: generated files are out of date with agent_sources/:", file=sys.stderr)
        _report("missing", result.create, sys.stderr)
        _report("stale", result.update, sys.stderr)
        _report("hand edited", [item.split(":", 1)[0] for item in result.conflicts], sys.stderr)
        _report("obsolete", result.remove, sys.stderr)
        if result.manifest_changed:
            _report("stale", [manifest.MANIFEST_PATH], sys.stderr)
        print("Run `just ci` locally and commit the regenerated files.", file=sys.stderr)
        return 1

    if result.conflicts:
        print("agentgen: refusing to overwrite; nothing was written:", file=sys.stderr)
        _report("conflict", result.conflicts, sys.stderr)
        print(HAND_EDIT_HINT, file=sys.stderr)
        return 1
    if not result.changed:
        print(f"agentgen: {len(outputs)} outputs are current")
        return 0
    publish.publish(root, outputs, manifest_bytes, result)
    print(f"agentgen ({GENERATOR}): regenerated from {SOURCES_DIR}/")
    _report("created", result.create)
    _report("updated", result.update)
    _report("overwrote hand edit", result.overwrite)
    _report("removed", result.remove)
    if result.manifest_changed:
        _report("updated", [manifest.MANIFEST_PATH])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return generate(args.root, check=args.check, accept_source=args.accept_source)
    except GenerationError as error:
        print("agentgen: generation failed; nothing was written:", file=sys.stderr)
        for problem in error.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
