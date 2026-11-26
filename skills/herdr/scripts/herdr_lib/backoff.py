"""Escalating retry delays for herdr_send waits."""

from __future__ import annotations

import secrets
from collections.abc import Iterator

DEFAULT_PROMPT_WAIT = 180.0
MAX_DELAY = 30.0
JITTER = 0.2

_RANDOM = secrets.SystemRandom()


def delays(first: float, max_delay: float = MAX_DELAY, jitter: float = JITTER) -> Iterator[float]:
    """Yield doubling delays from first, held at max_delay, each scaled by up to +/- jitter."""
    base = max(first, 0.0)
    while True:
        yield base * _RANDOM.uniform(1 - jitter, 1 + jitter)
        base = min(base * 2, max_delay) if base else 0.0
