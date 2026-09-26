# Agent Source Rework

## Status

This is a working record of decisions for reworking the shared agent sources in [cypher0n3/dotagents#2](https://github.com/cypher0n3/dotagents/pull/2).
It is updated after each answer and is not yet a specification.

## Problem Statement

The owner asked for one source, defined in one place, that is easy to update and generates every output.
The implementation in the pull request does not meet that goal.
Changing one agent today can touch up to four kinds of files:

- `agent_sources/roles/<name>.yaml` holds the agent's description, model alias, skills, restrictions, and Claude color.
- `agent_sources/prompts/<name>.md` holds the agent's instructions.
- `agent_sources/targets/<tool>.yaml`, one per tool, holds how each tool spells each field and each tool's model aliases.
- `agent_sources/templates/<tool>.<ext>.j2`, one per tool, wraps the rendered pieces.

The generator code lives separately in `tools/agentgen/`.

## Decisions

1. One file per agent is the whole source for that agent.
   Its YAML frontmatter holds everything about the agent, including its description, model, skills, read-only intent, tool list, and any per-tool overrides, and its Markdown body holds the instructions.
   Editing that one file changes the agent for every tool.
   How each tool spells each field is built into the generator code, which is not edited to change an agent.
   The separate `roles/`, `prompts/`, and per-tool profile files are removed.

2. The per-agent source files live in a new folder, `agent_sources/<name>.md`, one Markdown file per agent.
   The generator writes the Claude Code agent to `agents/<name>.md`, and the Codex, Cursor, Hermes, and CAI outputs under `generated/`.
   `just install`, `validate_agents.py`, and the hand-maintained agent index `agents/README.md` keep using `agents/` unchanged.
   The Claude Code agent is generated output, never the source.

3. An agent's model is a tier word, such as `model: strong`, with optional per-tool overrides in the same file.
   The generator code maps each tier to each tool's model; a tool with no mapping for the tier, and no override, uses its session's model.
   An override names one tool and a model identifier that tool understands, and wins over the tier for that tool only.

   ```yaml
   model:
     tier: strong
     cursor: grok[high]
   ```

4. There are four tiers, mapped for Claude Code as follows:
   - `frontier` maps to `fable`.
   - `strong` maps to `opus`, and is the tier for coder, reviewer, reviewer-go, and planner.
   - `standard` maps to `sonnet`, and is the tier for researcher, test-runner, spec-author, feature-author, and docs-writer.
   - `fast` maps to `haiku`.

   Codex, Cursor, and CAI have no tier mappings yet, so their agents use the session's model until mappings are added to the generator.
   Hermes personalities cannot set a model.
   The existing Claude Code agents therefore keep their current `model` values.

5. An agent source file uses flat keys that read like a Claude Code agent, plus one optional block per tool:

   ```yaml
   ---
   name: reviewer
   description: Performs adversarial review of ...
   model: strong
   color: red
   readonly: true
   tools: [Read, Grep, Glob, Bash]
   skills: [senior-developer, code-review-precision]
   suggested_skills: []
   codex:
     model_reasoning_effort: high
   ---
   # Reviewer
   ```

   - `color` applies only to Claude Code.
   - `readonly` and `tools` state intent; each tool enforces them where it can and states them as comments where it cannot.
   - `skills` are loaded before the agent starts, and `suggested_skills` when a task needs them.
   - A block named after a tool holds settings only that tool has.

   No tool reads a source file directly.
   The generator rejects any key it does not know, so a typo fails generation instead of being ignored.
   Each generated file carries only the keys its tool is known to accept, so a key one tool does not recognize never reaches that tool, and intent a tool cannot express appears there only as a comment.
   How each tool treats an unknown key is therefore not relied on, and has not been verified for Codex, Cursor, Hermes, or CAI.

6. Every agent is generated for every tool by default.
   An agent opts out of specific tools with an optional `exclude` list, such as `exclude: [hermes]`.
   Adding a new tool to the generator therefore needs no change to any agent file.

7. There is no Jinja anywhere: no templates in `agent_sources/`, and none in the generator.
   Each agent is one plain `agent_sources/<name>.md` file whose body is ordinary Markdown, linted like every other Markdown file, and the generator code writes every output directly.
   A review of the nine bodies found little that templating would serve.
   - Shared boilerplate is weak: all nine read the repository's `meta.md`, `AGENTS.md`, and `AGENTS.override.md`, but each ends that sentence differently for its role, and only one sentence is identical across three agents.
   - Eight lines across six agents are phrased for Claude Code: "you have no edit tools" in reviewer, reviewer-go, and researcher, and "the preloaded ... skill" in reviewer, reviewer-go, planner, and docs-writer.
     They are reworded once to be true for every tool, such as "Do not modify the workspace, and do not use the shell to work around that."

   The reworded lines change the Claude Code agents too, so those agents are no longer byte-identical to the current hand-authored files, and each change is listed in the pull request.

8. The generator is a standard-library-only Python script, `.ci_scripts/generate_agents.py`, with an offline unit test beside it in `.ci_scripts/test_generate_agents.py`.
   It parses a documented subset of YAML frontmatter itself: flat keys, lists, the `model` block, and one block per tool.
   Anything outside that subset, such as anchors, fails generation with a clear error.
   `tools/agentgen/`, `uv`, its lock file, and the `uv` install in both CI definitions are removed, so `just ci` again needs only `just`, `python3`, and `markdownlint-cli2`.

9. Generated files are not committed.
   `just ci` and `just install` both generate them with the same generator code, and the output paths are ignored by Git.
   - There is no generation manifest, no hand-edit protection, no accept-source recipe, and no check-only mode, because nothing generated is ever committed or reviewed as a file.
   - Hosted CI generates the outputs before any check that reads them, such as agent validation.
   - Each generated file still opens with a comment naming its source and saying not to edit it, where the format allows one, because a hand edit is lost at the next generation.
   - The Claude Code agents under `agents/` stop being committed, which revises decision 2's output location as decision 10 records.

10. Every generated file lives under one Git-ignored `generated/` folder, which revises decision 2's output location:
    - Claude Code: `generated/claude/agents/<name>.md`.
    - Codex: `generated/codex/agents/<name>.toml`.
    - Cursor: `generated/cursor/agents/<name>.md`.
    - Hermes: `generated/hermes/personalities/<name>.yaml`.
    - CAI: `generated/cai/personas/<name>.md`.

    The `agents/` folder is removed.
    The hand-maintained agent index moves from `agents/README.md` to `agent_sources/README.md`, beside the sources it describes.
    The generator owns `generated/` outright and clears and rebuilds it on every run, so a removed agent never leaves a stale output behind.
    The installers and `validate_agents.py` read the Claude Code agents from `generated/claude/agents/`.

11. The Windows installer, `scripts/install.ps1`, runs the same Python generator, found as `python` or through the `py` launcher, before any agent step.
    Without Python, it skips only the agent steps (Claude Code, Codex, and Cursor agents, and Hermes personalities), says why and how to install Python, and still installs skills, instructions, and settings.
    Windows and Unix therefore produce identical output from the same code.

12. The pull request's installer behaviors stay as built, repointed at `generated/`:
    - Codex and Cursor agents are linked on every install, like the skill links, with `--no-codex-agents` and `--no-cursor-agents`.
    - CAI personas are linked into `$XDG_CONFIG_HOME/cai/personas/`, falling back to `~/.config/cai/personas/`, only when that CAI configuration root exists, with `--no-cai-personas`.
    - Hermes personalities are set through `hermes config set`, added when absent, updated when this installer set them and nobody changed them since, and otherwise replaced only with `--force`; ownership is recorded in `install-state.json`, and `--no-hermes-personalities` and `--no-hermes` skip the step.
    - The Windows installer refreshes a hard link or copy it placed that no longer matches its source, and requires `-Force` for a file the user changed.
    - Existing files are never replaced silently, and files this repository does not provide are reported, never removed.

    Windows behavior matches Linux and macOS as closely as the platform allows.
    Where the two installers differ, the difference must be forced by the platform, such as symbolic links needing elevation or Developer Mode on Windows, and must be documented.

13. The Windows installer installs CAI personas with the same rule as the Unix installer.
    It uses `$env:XDG_CONFIG_HOME\cai\personas`, or `~\.config\cai\personas` when that variable is empty or blank, only when that CAI configuration folder already exists, and `-NoCaiPersonas` skips the step.
    Without the folder it reports that it was not found, as the Unix installer does.
    This does not claim that CAI supports Windows; the installer only acts where a CAI configuration already exists.

14. The Windows installer uses a symbolic link for each generated file when Windows allows one, and otherwise falls back to a hard link on the same drive, then a copy.
    It tests once per run whether it can create a symbolic link, which works with Developer Mode or an elevated shell, and reports which link type it used.
    With symbolic links, Windows behaves exactly like Unix, and installed agents always show the latest generation.
    With hard links or copies, it behaves as the pull request built it, including refreshing files it placed that went stale, so no administrator rights or Developer Mode are ever required.

15. Generated Markdown is not linted directly.
    `just lint-md` skips `generated/`, the same way it already skips symlinked skills, and the lint configuration files are unchanged.
    The agent bodies are linted as sources in `agent_sources/<name>.md`, and the hosted Markdown lint job is unchanged.
    The generator's unit tests render the text it adds to a body, the `## Skill Dependencies` section for Codex and Cursor, and check it against the Markdown rules a test can apply.

16. The rework lands on the same pull request, [cypher0n3/dotagents#2](https://github.com/cypher0n3/dotagents/pull/2), as ordinary commits on top of its branch, and its description is rewritten to match.
    The pull request is squashed when it merges, so the rejected approach does not reach `main`.
    [Shared Agent Templates](../specs/shared-agent-templates.md) is rewritten to match these decisions, and this record is folded into it and removed.

17. The `model` block names each tool's model directly, with `tier` as the fallback, and a separate top-level `effort` key sets reasoning effort.
    This revises decisions 3 and 5, and replaces the `codex: { model_reasoning_effort: ... }` example in decision 5.

    ```yaml
    model:
      claude: opus
      tier: strong
      cai:
        - ollama-local/qwen3.8:35b
        - ollama-local/qwen3.6:35b
        - ollama-local/qwen3.8:27b
      codex: gpt-6-astra
      cursor: grok4.7
    effort: high
    ```

    - The model identifiers in this example are illustrative and are not checked against any provider; the generator passes each tool's value through unchanged.
    - A key other than `tier` is a tool name, and its value is that tool's model.
      It is a single identifier for every tool except CAI, whose value may be an ordered preference list; a list for any other tool fails generation.
    - CAI identifiers must be backend-qualified (`<backend_id>/<model>`, such as `ollama-local/qwen3.8:35b`), provider-qualified (`<provider>.<model>`), or a configured alias, per CAI's model identifier format; `ollama-local` in the example is illustrative and must match a backend configured in CAI.
    - A tool's own value wins; otherwise `tier` is mapped through the generator's tier table for that tool; otherwise the tool uses its session's model.
    - The short form `model: strong` remains valid and means a tier with no per-tool values, and an agent with no `model` key uses each tool's session model.
    - `effort` is optional and takes `low`, `medium`, `high`, `xhigh`, or `max`, matching Claude Code.
      It renders as `effort` for Claude Code and `model_reasoning_effort` for Codex, where `max` becomes `xhigh`.
      Tools with no known effort field receive it as a comment, and Hermes receives it in its explainer.

18. The CAI target follows CAI's `usability_fixes` branch at `b1db6c5` (2026-09-25), recorded below under CAI evidence, rather than the original draft.
    - A single CAI model renders as `models.default`, and a list renders as `models.preferred`, never as the legacy `model` or `preferred_models` keys.
      CAI rewrites a persona file that uses the legacy keys on discovery, and would do so through the installer's symbolic link into `generated/`.
    - Required and suggested skills render natively as `required_skills` and `suggested_skills`.
    - `readonly`, `tools`, and `effort` have no CAI field, so they render as comments, which CAI's YAML parser ignores.
    - Personas are installed as symbolic links, which CAI now follows safely, so the dependency on a CAI change is gone.

19. CAI reads the dotagents agent sources natively, and dotagents stops generating and installing anything for CAI.
    This supersedes the CAI parts of decisions 10, 12, 13, and 18: there is no `generated/cai/`, no CAI installer step on either platform, and no `--no-cai-personas` switch.
    - CAI discovers `~/.agents/agent_sources/` as a persona layer below its project and global persona directories and above its built-in personas, the same way it already discovers `~/.agents/skills/`.
    - CAI maps the dotagents format itself: `model.cai` becomes `models.default` for a single identifier or `models.preferred` for a list, `skills` becomes `required_skills`, `suggested_skills` is used as is, `exclude: [cai]` hides the agent, and keys for other tools are ignored.
    - An optional `cai:` block in a source file carries CAI-only settings: `selection`, `max_steps`, `max_turns`, `ingest_personas`, and `mcp_servers`.
      The dotagents generator validates that block, so a typo fails `just ci`, but renders nothing from it.
    - CAI never writes into `~/.agents/agent_sources/`: no legacy-key rewrite, and no `/models` write.
    - `/models` persistence for a persona from that layer writes a models-only overlay in CAI's own global persona directory, which CAI merges over the dotagents persona instead of replacing it.
    - Each source file carries `schema: 1`, so CAI can refuse a format version it does not understand.
    - Until CAI ships this reader, CAI does not see these agents, and its built-in personas are unaffected.
    - The CAI-side change is described in a requirements note under `docs/draft_specs/` for the owner to carry to CAI, since this session cannot push to GitLab.

## CAI Evidence

Read from `https://gitlab.com/cypher_zero/cai`, branch `usability_fixes`, commit `b1db6c59bda7c77620380062fb67172bd0f1f190` (2026-09-25), in `docs/tech_specs/personas.md`, `docs/tech_specs/inference/model_selection.md`, and `internal/personas/`.

- A persona is Markdown with YAML front matter holding `name` and `description` (required), `models.default`, `models.preferred`, `models.selection` (`auto` or `lock`), `max_steps`, `max_turns`, `required_skills`, `suggested_skills`, `ingest_personas`, and `mcp_servers`.
- The legacy `model` and `preferred_models` keys are still read, but discovery rewrites a writable file that uses them to the `models` keys, leaving the body byte-identical.
- Front matter is parsed with a non-strict YAML decoder, so unknown keys and comments are ignored.
- A persona read follows a symbolic link to its final target, requires a regular file, and verifies the opened file is the one it inspected.
- Discovery layers are project `.cai/personas/`, then the global directory `$XDG_CONFIG_HOME/cai/personas/` (default `~/.config/cai/personas/`, overridable by the `personas.dir` configuration key), then built-in personas; the first match wins and fields never merge.
- Model identifiers are an alias, `<backend_id>/<model>`, `<provider>.<model>`, or an unqualified name matching a known provider pattern such as `claude-*`.
- There is no persona field for reasoning effort, read-only intent, or a tool allowlist.
- Persisting a model from CAI's `/models` command writes `models.default` or `models.selection` into the global persona file `<personas dir>/<name>.md`, which follows a symbolic link into `generated/`.

## Open Questions

None; decision 19 resolves the `/models`, `personas.dir`, and `cai:` block questions, because CAI no longer receives generated or installed files.
