#!/usr/bin/env python3
"""Generate every tool's agent files from the sources in agent_sources/.

Each agent is one Markdown file, agent_sources/<name>.md. Its YAML front matter
holds everything about the agent, and its body holds the agent's instructions.
This script turns each source into:

- a Claude Code agent, generated/claude/agents/<name>.md
- a Codex custom agent, generated/codex/agents/<name>.toml
- a Cursor agent, generated/cursor/agents/<name>.md
- a Hermes personality, generated/hermes/personalities/<name>.yaml

generated/ is ignored by Git and rebuilt from scratch on every run, by both
`just ci` and the installers. CAI reads agent_sources/ itself, so nothing is
generated for it.

The work is split across three modules beside this script, all standard
library only:

- agent_front_matter.py parses the documented YAML subset sources use.
- agent_source.py validates each source into an Agent.
- agent_render.py writes an Agent in each tool's format.

This script renders every agent and replaces generated/ with the result.

Exit status is 0 when every agent was generated, and 1 when any source is
invalid, in which case every problem is printed and generated/ is left as it
was.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from agent_front_matter import SourceError
from agent_render import RENDERERS
from agent_source import Agent, load_agents

OUTPUT_DIR = "generated"

# The tools this script writes files for. CAI is also a target, but reads
# agent_sources/ itself.
GENERATED_TOOLS = ("claude", "codex", "cursor", "hermes")

# Where each tool's file goes, relative to generated/.
OUTPUT_PATHS = {
    "claude": "claude/agents/{name}.md",
    "codex": "codex/agents/{name}.toml",
    "cursor": "cursor/agents/{name}.md",
    "hermes": "hermes/personalities/{name}.yaml",
}


def render_all(agents: list[Agent]) -> dict[str, str]:
    """Return each output path, relative to generated/, with its content."""
    outputs: dict[str, str] = {}
    for agent in agents:
        for tool in GENERATED_TOOLS:
            if tool in agent.exclude:
                continue
            path = OUTPUT_PATHS[tool].format(name=agent.name)
            try:
                outputs[path] = RENDERERS[tool](agent)
            except SourceError as error:
                raise SourceError(f"{agent.path}: {error}") from error
    return outputs


def write_outputs(output: Path, outputs: dict[str, str]) -> None:
    """Replace the output directory with exactly these files.

    The new tree is built in a temporary directory beside the old one and then
    swapped in, so a failure part-way leaves the previous tree in place, and an
    agent that was removed leaves no stale file behind.
    """
    output = output.absolute()
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise SourceError(f"{output} must be a directory, not a link or file")
    output.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for relative, content in outputs.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            # newline="\n" keeps LF endings on Windows too.
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)

        retired = None
        if output.exists():
            retired = output.with_name(f".{output.name}.old-{os.getpid()}")
            output.rename(retired)
        staging.rename(output)
        if retired is not None:
            shutil.rmtree(retired)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: this script's repository)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output directory (default: <root>/generated)",
    )
    args = parser.parse_args(argv)
    output = args.output or args.root / OUTPUT_DIR

    try:
        agents = load_agents(args.root)
        outputs = render_all(agents)
        write_outputs(output, outputs)
    except SourceError as error:
        print("generate_agents: nothing was generated:", file=sys.stderr)
        for line in str(error).splitlines():
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"generate_agents: {len(outputs)} files for {len(agents)} agents in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
