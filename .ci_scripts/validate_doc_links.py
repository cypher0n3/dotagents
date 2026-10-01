#!/usr/bin/env python3
"""Validate relative Markdown links and heading anchors in this repository.

Every relative link target must exist on disk, and every in-document or
cross-document anchor must match a heading slug or an explicit HTML anchor id.
External links (http, https, mailto) are not fetched or checked.

Exit status is 0 when every link resolves and 1 when any link is broken.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

INLINE_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
HTML_ANCHOR_PATTERN = re.compile(r"<a\s+id=\"([^\"]+)\"")
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")

SKIPPED_DIRS = {
    ".git",
    ".markdownlint-repo",
    ".markdownlint-rules",
    ".venv",
    "__pycache__",
    "node_modules",
    "output",
    "tmp",
    "wip",
}
EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp://")


def slugify(heading_text: str) -> str:
    """Convert heading text into the GitHub-style anchor slug it produces."""
    text = re.sub(r"`([^`]*)`", r"\1", heading_text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_~]", "", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text)


def collect_anchors(path: Path) -> set[str]:
    """Return every anchor a document defines, from headings and HTML anchors."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        anchors.update(HTML_ANCHOR_PATTERN.findall(line))
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        slug = slugify(match.group(2))
        if not slug:
            continue
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(f"{slug}-{count}" if count else slug)
    return anchors


def extract_links(path: Path) -> list[tuple[int, str]]:
    """Return the relative link targets in a document with their line numbers."""
    links: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for target in INLINE_LINK_PATTERN.findall(line):
            if target.startswith(EXTERNAL_SCHEMES) or target.startswith("<"):
                continue
            links.append((number, target))
    return links


def discover_markdown(root: Path) -> list[Path]:
    """Return every Markdown file under the root, skipping generated directories."""
    found: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIPPED_DIRS for part in path.relative_to(root).parts):
            continue
        found.append(path)
    return found


def validate_link(source: Path, root: Path, target: str, anchor_cache: dict[Path, set[str]]) -> str | None:
    """Return an error message when the link does not resolve, otherwise None."""
    path_part, _, anchor = target.partition("#")

    if not path_part:
        resolved = source
    else:
        resolved = (source.parent / path_part).resolve()
        if not resolved.exists():
            return f"link target does not exist: {target}"
        if resolved.is_dir():
            return None if not anchor else f"directory link cannot carry an anchor: {target}"

    if not anchor:
        return None
    if resolved.suffix.lower() != ".md":
        return None
    if resolved not in anchor_cache:
        anchor_cache[resolved] = collect_anchors(resolved)
    if anchor.lower() not in {value.lower() for value in anchor_cache[resolved]}:
        location = "this document" if resolved == source else str(resolved.relative_to(root))
        return f"anchor '#{anchor}' not found in {location}"
    return None


def main(argv: list[str] | None = None) -> int:
    """Validate every relative Markdown link under the requested root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="repository root to scan (default: .)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1

    anchor_cache: dict[Path, set[str]] = {}
    errors: list[str] = []
    documents = discover_markdown(root)
    for document in documents:
        for number, target in extract_links(document):
            problem = validate_link(document, root, target, anchor_cache)
            if problem:
                errors.append(f"{document.relative_to(root)}:{number}: {problem}")

    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(f"\nvalidate_doc_links: {len(errors)} broken link(s) in {len(documents)} document(s)", file=sys.stderr)
        return 1
    print(f"validate_doc_links: {len(documents)} document(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
