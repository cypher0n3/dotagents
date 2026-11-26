"""Saved herdr_send messages: one file per message, delivered oldest first.

Layout under the state root (HERDR_SEND_STATE_DIR, else $XDG_STATE_HOME/herdr-send, else
~/.local/state/herdr-send):

    <server>/<pane>/<id>.json        waiting for delivery
    <server>/<pane>/<id>.sending     claimed by one sender (atomic rename) while it sends
    <server>/<pane>/sent/<id>.json   delivered; read once by the original sender
    <server>/<pane>/dead/<id>.json   never sent (expired, pane gone, interrupted, or dropped)

Files are JSON because the scripts are stdlib-only; `pending list --yaml` shows them as YAML.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIN_TTL = 1800.0
SENDING_STALE = 60.0
SENT_KEEP = 3600.0
DEAD_KEEP = 7 * 86400.0


def state_root() -> Path:
    """Return the state root directory."""
    override = os.environ.get("HERDR_SEND_STATE_DIR")
    if override:
        return Path(override)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "herdr-send"


def server_key() -> str:
    """Name the herdr server by a short hash of its socket path, since pane IDs are per server."""
    socket = os.environ.get("HERDR_SOCKET_PATH", "")
    return hashlib.sha256(socket.encode()).hexdigest()[:12] if socket else "default"


def iso(ts: float) -> str:
    """Format a timestamp as UTC ISO 8601."""
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def new_message_id(now: float) -> str:
    """Return a message ID that sorts by creation time."""
    stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{secrets.token_hex(3)}"


def _private_dir(path: Path) -> Path:
    """Create path (and parents) as a user-only directory."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def _write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically with user-only permissions."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _read(path: Path) -> dict[str, Any] | None:
    """Read one record, or None when it is gone or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


class PaneStore:
    """Saved messages for one target pane on one herdr server."""

    def __init__(self, pane_id: str, root: Path | None = None):
        self.pane_id = pane_id
        self.dir = (root or state_root()) / server_key() / pane_id.replace(":", "-").replace("/", "-")

    def _path(self, message_id: str, suffix: str = ".json", sub: str | None = None) -> Path:
        return (self.dir / sub if sub else self.dir) / f"{message_id}{suffix}"

    def save(self, record: dict[str, Any]) -> None:
        """Save a new waiting message."""
        _private_dir(self.dir)
        _write(self._path(record["message_id"]), record)

    def update(self, message_id: str, **fields: Any) -> bool:
        """Merge fields into a waiting message; False when it is no longer waiting."""
        path = self._path(message_id)
        record = _read(path)
        if record is None:
            return False
        record.update(fields)
        _write(path, record)
        return True

    def waiting(self) -> list[dict[str, Any]]:
        """Return waiting messages, oldest first."""
        if not self.dir.is_dir():
            return []
        records = (_read(p) for p in sorted(self.dir.glob("*.json")))
        return [r for r in records if r is not None]

    def claim(self, message_id: str, claimed_by: str | None) -> dict[str, Any] | None:
        """Claim a waiting message by atomic rename; None when another sender got it first."""
        src, dst = self._path(message_id), self._path(message_id, ".sending")
        try:
            os.rename(src, dst)
        except FileNotFoundError:
            return None
        record = _read(dst) or {"message_id": message_id}
        record.update(claimed_by=claimed_by, claimed_at=iso(time.time()))
        _write(dst, record)
        return record

    def release(self, message_id: str, **fields: Any) -> None:
        """Return a claimed message to waiting after a failed send."""
        src = self._path(message_id, ".sending")
        record = _read(src)
        if record is None:
            return
        record.update(fields)
        _write(src, record)
        os.rename(src, self._path(message_id))

    def mark_sent(self, message_id: str, delivered_by: str | None) -> None:
        """Record a claimed message as delivered."""
        src = self._path(message_id, ".sending")
        record = _read(src) or {"message_id": message_id}
        record.update(delivered_by=delivered_by, delivered_at=iso(time.time()))
        _private_dir(self.dir / "sent")
        _write(self._path(message_id, sub="sent"), record)
        src.unlink(missing_ok=True)

    def take_sent(self, message_id: str) -> dict[str, Any] | None:
        """Read and remove the delivery record for a message another sender delivered."""
        path = self._path(message_id, sub="sent")
        record = _read(path)
        if record is not None:
            path.unlink(missing_ok=True)
        return record

    def kill(self, message_id: str, reason: str, suffix: str = ".json") -> dict[str, Any] | None:
        """Move a message to dead/ with a reason; it is never sent."""
        src = self._path(message_id, suffix)
        record = _read(src)
        if record is None:
            return None
        record.update(dead_reason=reason, dead_at=iso(time.time()), reported=False)
        _private_dir(self.dir / "dead")
        _write(self._path(message_id, sub="dead"), record)
        src.unlink(missing_ok=True)
        return record

    def dead(self, message_id: str) -> dict[str, Any] | None:
        """Return a dead record, if any."""
        return _read(self._path(message_id, sub="dead"))

    def sweep(self, now: float) -> None:
        """Expire old waiting messages, retire stuck claims, and prune old records."""
        if not self.dir.is_dir():
            return
        for record in self.waiting():
            if record.get("expires_ts", now + 1) <= now:
                self.kill(record["message_id"], "expired")
        for path in self.dir.glob("*.sending"):
            if now - path.stat().st_mtime > SENDING_STALE:
                # The sender died mid-send; it may have been delivered, so never resend it.
                self.kill(path.stem, "interrupted_during_send", ".sending")
        for sub, keep in (("sent", SENT_KEEP), ("dead", DEAD_KEEP)):
            for path in (self.dir / sub).glob("*.json") if (self.dir / sub).is_dir() else ():
                if now - path.stat().st_mtime > keep:
                    path.unlink(missing_ok=True)

    def unreported_dead(self) -> list[dict[str, Any]]:
        """Return dead records not yet reported, marking them reported."""
        out = []
        dead_dir = self.dir / "dead"
        for path in sorted(dead_dir.glob("*.json")) if dead_dir.is_dir() else ():
            record = _read(path)
            if record and not record.get("reported"):
                record["reported"] = True
                _write(path, record)
                out.append(summarize(record))
        return out

    def all_dead(self) -> list[dict[str, Any]]:
        """Return every dead record."""
        dead_dir = self.dir / "dead"
        records = (_read(p) for p in sorted(dead_dir.glob("*.json"))) if dead_dir.is_dir() else ()
        return [summarize(r) for r in records if r]


def summarize(record: dict[str, Any]) -> dict[str, Any]:
    """Return the report view of a record, without the full message text."""
    keys = ("message_id", "created", "expires", "attempts", "last_refusal", "dead_reason", "sender_pane")
    view = {k: record[k] for k in keys if k in record}
    text = record.get("text", "")
    view["text_preview"] = text[:80] + ("..." if len(text) > 80 else "")
    return view


def all_pane_stores(root: Path | None = None) -> list[PaneStore]:
    """Return a store for every pane with saved state on this server."""
    base = (root or state_root()) / server_key()
    if not base.is_dir():
        return []
    stores = []
    for path in sorted(p for p in base.iterdir() if p.is_dir()):
        record = next((_read(f) for f in sorted(path.glob("*.json"))), None)
        if record is None:
            record = next((_read(f) for f in sorted(path.glob("dead/*.json"))), None)
        stores.append(PaneStore((record or {}).get("pane_id", path.name), root))
    return stores
