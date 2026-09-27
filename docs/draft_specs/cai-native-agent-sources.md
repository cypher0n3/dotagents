# CAI Native Agent Sources

## Status

This is a requirements note for a change to CAI, kept here so it can be carried to the CAI repository.
It describes what CAI needs to read the `dotagents` agent sources directly, as decided in [Shared Agent Templates](../specs/shared-agent-templates.md#cai).
It was written against CAI's `usability_fixes` branch at `b1db6c59bda7c77620380062fb67172bd0f1f190`.

## Background

`dotagents` keeps each agent as one file, `~/.agents/agent_sources/<name>.md`, with YAML front matter and a Markdown body.
CAI already discovers `~/.agents/skills/` natively, and should discover these agents the same way instead of receiving generated persona files.

## Requirements

Each requirement below is stated for CAI's persona loading.

### Discovery Layer

- CAI adds `~/.agents/agent_sources/` as a persona discovery layer below the project `.cai/personas/` and global persona directories and above its built-in personas.
- The layer is scanned for top-level `*.md` files, and `README.md` is skipped because it is the agent index.
- The layer is watched like the other persona layers.
- A file whose `schema` is not a version CAI supports is skipped with a diagnostic naming the file and version.
- A file whose `exclude` list contains `cai` is skipped silently.

### Field Mapping

- `name` and `description` are used as they are.
- `model.cai` becomes `models.default` when it is a single identifier, or `models.preferred` when it is a list, in order.
- `model.tier` and the other tools' keys under `model` are ignored.
- `skills` becomes `required_skills`, and `suggested_skills` is used as it is.
- The optional `cai` block supplies `selection` as `models.selection`, and `max_steps`, `max_turns`, `ingest_personas`, and `mcp_servers` as they are.
- The keys `effort`, `color`, `readonly`, `tools`, `exclude`, and blocks for other tools are ignored.
- The Markdown body is the persona prompt, unchanged.

### Writes

- CAI never rewrites legacy keys in this layer.
- The only write CAI makes to a file in this layer is persisting a model with `/model`: it places the selected identifier at the top of that agent's `model.cai` list, moving it up if it is already listed, and turning a single identifier into a list.
- That write changes nothing else in the file: other keys, their order, comments, and the body stay byte-identical, so the change shows up as an ordinary diff in the `dotagents` clone.
- A write follows the same symbolic-link and file-identity rules CAI already applies to persona reads.

## Open Points

- Whether persisting `models.selection` from `/model` also writes into the source file, or stays in CAI's own configuration.
- Whether CAI should honor a `dotagents` clone outside `~/.agents`, for example through a configuration key.
