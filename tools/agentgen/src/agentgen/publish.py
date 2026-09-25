"""Compare rendered outputs with the checkout, then check or publish them.

A managed file is one the committed manifest lists. Publication protects hand
edits: a managed file whose bytes match neither the digest recorded at the last
generation nor the new rendering was edited by hand, and a file the manifest
does not list that sits at an output path is not the generator's to replace.
Either stops publication unless the caller accepts the sources as the truth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from agentgen.errors import GenerationError
from agentgen.manifest import MANIFEST_PATH, digest
from agentgen.sources import OUTPUT_ROOTS

TEMP_SUFFIX = ".agentgen-tmp"


@dataclass
class Plan:
    """What publication would do, and why it might refuse."""

    create: list[str] = field(default_factory=list)
    update: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    overwrite: list[str] = field(default_factory=list)
    manifest_changed: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.create or self.update or self.remove or self.overwrite or self.manifest_changed)


def _check_path(root: Path, relative: str, label: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative or not pure.parts:
        raise GenerationError(f"{label}: '{relative}' is not a clean relative path")
    if pure.parts[0] not in OUTPUT_ROOTS or len(pure.parts) < 2:
        raise GenerationError(f"{label}: '{relative}' is outside {' and '.join(OUTPUT_ROOTS)}/")
    if pure.parts[0] == "agents" and pure.name.lower() == "readme.md":
        raise GenerationError(f"{label}: '{relative}' is the hand-maintained agent index")
    current = root
    for part in pure.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise GenerationError(f"{label}: '{relative}' passes through a symlink at {current.relative_to(root)}")
    path = root / relative
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise GenerationError(f"{label}: '{relative}' exists and is not a regular file")
    return path


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _check_collisions(root: Path, outputs: dict[str, bytes]) -> None:
    folded: dict[str, str] = {}
    for relative in outputs:
        key = relative.casefold()
        if key in folded:
            raise GenerationError(f"outputs '{folded[key]}' and '{relative}' collide on a case-insensitive filesystem")
        folded[key] = relative
    for relative in outputs:
        parent = (root / relative).parent
        if not parent.is_dir():
            continue
        name = PurePosixPath(relative).name
        for entry in parent.iterdir():
            if entry.name != name and entry.name.casefold() == name.casefold():
                raise GenerationError(f"output '{relative}' collides with existing '{entry.relative_to(root)}'")


def plan(root: Path, outputs: dict[str, bytes], manifest: bytes, recorded: dict[str, str] | None,
         *, accept_source: bool) -> Plan:
    """Classify every output and managed file without changing anything."""
    recorded = recorded or {}
    for relative in list(outputs) + list(recorded):
        _check_path(root, relative, "output")
    _check_path(root, MANIFEST_PATH, "manifest")
    _check_collisions(root, outputs)

    result = Plan()
    for relative, content in sorted(outputs.items()):
        disk = _read(root / relative)
        if disk == content:
            continue
        if disk is None:
            result.create.append(relative)
        elif recorded.get(relative) == digest(disk):
            result.update.append(relative)
        elif accept_source:
            result.overwrite.append(relative)
        elif relative in recorded:
            result.conflicts.append(f"{relative}: edited by hand since it was generated")
        else:
            result.conflicts.append(f"{relative}: not listed in {MANIFEST_PATH}, so it is not the generator's to replace")
    for relative in sorted(set(recorded) - set(outputs)):
        disk = _read(root / relative)
        if disk is None:
            continue
        if digest(disk) == recorded[relative]:
            result.remove.append(relative)
        elif accept_source:
            result.overwrite.append(relative)
        else:
            result.conflicts.append(f"{relative}: no longer generated, but edited by hand since it was")
    result.manifest_changed = _read(root / MANIFEST_PATH) != manifest
    return result


def _stage(path: Path, content: bytes) -> Path:
    temp = path.with_name(f".{path.name}{TEMP_SUFFIX}")
    if temp.is_symlink() or temp.exists():
        temp.unlink()
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return temp


def publish(root: Path, outputs: dict[str, bytes], manifest: bytes, result: Plan) -> None:
    """Stage every changed file, then move them into place, finishing with the manifest."""
    writes = {relative: outputs[relative] for relative in result.create + result.update
              + [item for item in result.overwrite if item in outputs]}
    removals = result.remove + [item for item in result.overwrite if item not in outputs]
    if result.manifest_changed or writes or removals:
        writes[MANIFEST_PATH] = manifest
    staged: list[tuple[Path, Path]] = []
    try:
        for relative, content in writes.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            _check_path(root, relative, "output")
            staged.append((_stage(path, content), path))
    except BaseException:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
        raise
    # The manifest moves last, so an interrupted run leaves files that match
    # the new rendering, which the next run recognizes as current, and
    # obsolete files still listed, which the next run removes.
    manifest_path = root / MANIFEST_PATH
    for temp, path in staged:
        if path != manifest_path:
            os.replace(temp, path)
    for relative in removals:
        (root / relative).unlink(missing_ok=True)
    for temp, path in staged:
        if path == manifest_path:
            os.replace(temp, path)
