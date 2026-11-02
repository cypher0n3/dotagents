# `AGENTS.md`

## General Instructions

- Look for and read repo-local `meta.md` file if it exists.
- Look for and read repo-local `AGENTS.override.md` if it exists.
- For structured data outputs that are saved to a file or meant to be read/interpreted by humans (even in stdout for example), ALWAYS prefer YAML over JSON, NDJSON, etc. whenever possible.

## Commits

- Do NOT add trailers to commit messages or pull requests unless I explicitly authorize them; this includes `Co-Authored-By`, session links, and generated-with notices.

## Worktrees

- NEVER create a git worktree inside the project directory, including under `.claude/worktrees/`; repository-wide tooling run from the main checkout sweeps nested worktrees in with it.
- Create worktrees outside the project, as siblings of its other worktrees (for example `~/projects/personal/<project>_wtN`).

## Asking Questions

- Do NOT use the question or ask tool provided by the harness.
- Use the `grill-me` skill instead.
