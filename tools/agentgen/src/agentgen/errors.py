"""Errors raised while loading, rendering, or publishing agent sources."""

from __future__ import annotations


class GenerationError(Exception):
    """One or more problems that stop generation before anything is published."""

    def __init__(self, problems: list[str] | str):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("\n".join(self.problems))
