# Markdown Conventions

## Overview

This repository lints every Markdown file with `markdownlint-cli2`, using the built-in rules plus the custom rules from [docs-as-code-tools](https://github.com/cypher0n3/docs-as-code-tools).
The configuration lives in [`.markdownlint.yml`](../../.markdownlint.yml) and [`.markdownlint-cli2.jsonc`](../../.markdownlint-cli2.jsonc), and both files are off limits to agents.
This document explains the conventions those files enforce so a contributor does not have to read rule source to understand a failure.

## Prose Formatting

Documentation prose follows one sentence per line, with no hard wrapping inside a sentence.
Line length is effectively unlimited, so a long sentence stays on one line and a diff shows exactly which sentence changed.

- Write in US (American) English.
- Use ASCII characters only, outside the [`README.md`](../../README.md) badges and highlights.
  Write a hyphen rather than an em dash, and straight quotes rather than curly quotes.
- Use dashes for unordered list items, never asterisks.
- Use fenced code blocks with a language label, never indented code blocks.

## Document Structure

Every document opens with a single H1 and puts content under every heading it introduces.

- Only badges or a table of contents may sit between the H1 and the first H2.
- An H2 or deeper heading must have at least one line of content directly beneath it, before any subheading.
- Headings use AP-style title case and must not repeat, even after case and whitespace are normalized.
- Do not use a bold line as a pseudo-heading; promote it to a real heading.
- Keep a document under 1500 lines.

## Tables and Links

Use lists rather than pipe tables.
Lists survive diffs and agent edits better, and the lint reports a table with the list form it wants instead.

Internal links are relative paths to files in this repository, checked by `just validate-doc-links` along with any heading anchor they carry.
Anchors follow the usual GitHub slug of the heading text, so a link must be updated when the heading it points at is reworded.

## Exemptions for Skill Files

Files under [`skills/`](../../skills/README.md) are prompt content, so three rules do not apply to them.

- `no-h1-content` is off, because a `SKILL.md` body starts immediately under its H1.
- `no-empty-heading` is off, because long prompts use bare grouping headings.
- `no-heading-like-lines` is off, because bold labels are deliberate inline emphasis for an agent.

Every other rule, including one sentence per line, applies to skill files exactly as it does to repository documentation.

## Running the Checks

Run `just install-markdownlint` once to fetch the custom rules into the ignored `.markdownlint-rules/` directory.
After that, `just lint-md` fixes what it can and reports the rest, and `just docs-check` adds link validation.
Under CI, where the `CI` environment variable is set, `just lint-md` only checks, so anything it would fix fails the run.
