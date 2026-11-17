---
name: just-ci
description: "Runs relevant tests and quick lint checks while working, and the full gate, such as `just ci`, before merge. Use this skill when changing code in any repository."
user-invocable: true
---
# `just ci` Before Merge

## While Working

Run the tests for the code you touched and any failing test, plus the linters and formatters for the files you changed.
Prefer the project's own recipes, then the commands its CI runs.
Leave full suites, slow end-to-end or integration runs, and the full gate for merge unless the task asks for them.
Report which checks you ran and their results.

## Before Merge

Run the full gate when the change is ready to land, or when the task or repository rules ask; one passing run covers a batch landing together.
The full gate is the first the repository has of `just ci`, its `make` equivalent, or the checks its CI configuration or contributing guide runs; say which you used.
With none, run the full test suite and configured linters, and report that there is no single gate rather than inventing one.
Run it as its own shell call, read its exit status, and fix every issue it reports, whatever caused it.

## Not Allowed

Suppressing linters, modifying configs, the justfiles, or their `make` and CI equivalents, and reverting uncommitted changes are NOT ALLOWED.
