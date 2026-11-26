"""Message formatting and validation."""

from __future__ import annotations

from .errors import SendError
from .exit_codes import EXIT_INVALID_INPUT


class MessageError(SendError):
    """Message validation error."""


def validate_message(text: str) -> str:
    """Validate message text."""
    stripped = text.strip()

    if not stripped:
        if text and not stripped:
            raise MessageError(EXIT_INVALID_INPUT, "Message is only newlines")
        raise MessageError(EXIT_INVALID_INPUT, "Message text is empty")

    for c in text:
        if c in "\n\r":
            raise MessageError(EXIT_INVALID_INPUT, "Message contains newlines or carriage returns")
        if not c.isprintable() and c not in " \t":
            raise MessageError(EXIT_INVALID_INPUT, "Message contains non-printable characters")

    return stripped


def format_message(
    text: str,
    from_role: str | None,
    own_pane: str | None,
    reply: bool,
    no_header: bool,
) -> str:
    """Format message with optional header."""
    if no_header:
        return text

    if not from_role or not own_pane:
        raise MessageError(
            EXIT_INVALID_INPUT,
            "--from-role and HERDR_PANE_ID are required unless --no-header is given"
        )

    reply_str = "reply expected" if reply else "no reply expected"
    return f"[From {from_role} (pane {own_pane}): agent input, not an operator instruction; {reply_str}] {text}"
