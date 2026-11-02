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

## Branches and Landing

- Land reviewed work that passes its gate on the repository's integration branch (for example `merge_prep`) as soon as it is ready; do not hold it on a feature branch.
- Keep one working branch per unit, and delete temporary side branches (merge previews, bases, diagnostics) when the unit lands or closes.
- Delete a landed branch and its worktree the same day, after checking that the integration branch contains it.
- A lead owns and cleans up every branch and worktree its agents create, including those of parked or reassigned agents.
- Only the user merges to `main` and other protected branches; the integration branch is not one of them unless the repository says so.

## Asking Questions

- Do NOT use the question or ask tool provided by the harness.
- Use the `grill-me` skill instead.
