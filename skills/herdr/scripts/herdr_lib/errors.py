"""Base errors for herdr_send."""

from __future__ import annotations

_DEFAULT_REASONS = {
    10: "busy",
    11: "blocked",
    12: "not_ready",
    13: "target_error",
    14: "not_in_herdr",
    20: "herdr_error",
    21: "invalid_input",
}


class SendError(Exception):
    """Base error with exit code and a short machine-readable reason."""

    def __init__(self, exit_code: int, message: str, reason: str | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message
        self.reason = reason or _DEFAULT_REASONS.get(exit_code, "error")
