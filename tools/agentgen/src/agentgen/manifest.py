"""Build and read the deterministic generation manifest."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agentgen import GENERATOR, yamlio
from agentgen.errors import GenerationError
from agentgen.render import Rendered
from agentgen.sources import SCHEMA_VERSION, SOURCES_DIR, Sources

MANIFEST_PATH = "generated/manifest.yaml"


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build(root: Path, sources: Sources, rendered: list[Rendered]) -> bytes:
    """Return the manifest bytes for one generation; identical inputs give identical bytes."""
    templates_dir = root / SOURCES_DIR / "templates"
    templates = {
        profile.template: digest((templates_dir / profile.template).read_bytes())
        for profile in sorted(sources.profiles.values(), key=lambda item: item.template)
    }
    targets: dict[str, Any] = {}
    for name in sorted(sources.profiles):
        profile = sources.profiles[name]
        targets[name] = {
            "source": profile.path,
            "digest": digest(profile.text.encode("utf-8")),
            "application": profile.application["name"],
            "checked": profile.application["checked"],
            "template": profile.template,
        }
    roles: dict[str, Any] = {}
    for name in sorted(sources.roles):
        role = sources.roles[name]
        outputs: dict[str, Any] = {}
        for item in rendered:
            if item.role != name:
                continue
            model: dict[str, Any] = {"rule": item.model_rule}
            if item.model_value is not None:
                model["value"] = item.model_value
            outputs[item.target] = {
                "path": item.path,
                "digest": digest(item.content),
                "model": model,
                "notes": list(item.notes),
            }
        roles[name] = {
            "source": role.path,
            "digest": digest(role.text.encode("utf-8")),
            "body": f"{SOURCES_DIR}/{role.body_path}",
            "body_digest": digest(role.body.encode("utf-8")),
            "outputs": outputs,
        }
    document = {
        "generator": GENERATOR,
        "schema": SCHEMA_VERSION,
        "templates": templates,
        "targets": targets,
        "roles": roles,
        "outputs": [{"path": item.path, "digest": digest(item.content)}
                    for item in sorted(rendered, key=lambda entry: entry.path)],
    }
    return yamlio.dump_document(document).encode("utf-8")


def recorded_outputs(root: Path) -> dict[str, str] | None:
    """Return the path-to-digest map from the committed manifest, or None when there is none."""
    path = root / MANIFEST_PATH
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise GenerationError(f"{MANIFEST_PATH}: must be a regular file")
    try:
        data = yamlio.load(path, MANIFEST_PATH)
    except GenerationError as error:
        raise GenerationError(error.problems + [f"{MANIFEST_PATH}: rerun with --accept-source to rebuild it"]) from error
    entries = data.get("outputs") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and isinstance(entry.get("path"), str) and isinstance(entry.get("digest"), str)
        for entry in entries
    ):
        raise GenerationError(f"{MANIFEST_PATH}: has no valid outputs list; rerun with --accept-source to rebuild it")
    return {entry["path"]: entry["digest"] for entry in entries}
