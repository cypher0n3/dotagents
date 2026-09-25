"""Render validated roles into each target's native file.

Each target's adapter builds an ordered list of native entries and fixed
comment blocks from the role and the target profile, then hands the serialized
text to a thin Jinja template. Role text is always passed to templates as data
and is never itself compiled as a template.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from agentgen import tomlio, yamlio
from agentgen.errors import GenerationError
from agentgen.sources import SOURCES_DIR, Capability, Profile, Role

SKILLS_HEADING = "## Skill Dependencies"
_H2 = re.compile(r"^## ")
_FENCE = re.compile(r"^(```|~~~)")


@dataclass
class Rendered:
    """One rendered output file and what the generator decided while rendering it."""

    role: str
    target: str
    path: str
    content: bytes
    model_rule: str
    model_value: str | list[str] | None
    notes: list[str] = field(default_factory=list)


@dataclass
class _Document:
    """The pieces of one output before serialization."""

    entries: list[tuple[str, Any]] = field(default_factory=list)
    comments: list[list[str]] = field(default_factory=list)
    order: list[tuple[str, int]] = field(default_factory=list)
    required_instruction: list[str] = field(default_factory=list)
    suggested_instruction: list[str] = field(default_factory=list)
    explainer: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, key: str, value: Any) -> None:
        self.order.append(("entry", len(self.entries)))
        self.entries.append((key, value))

    def comment(self, lines: list[str]) -> None:
        self.order.append(("comment", len(self.comments)))
        self.comments.append(lines)

    def native(self) -> dict[str, Any]:
        return dict(self.entries)


def resolve_model(role: Role, profile: Profile) -> tuple[str, str | list[str] | None]:
    """Return the rule that selected the model and the resolved value, or inherit."""
    if profile.name in role.model_direct:
        value = role.model_direct[profile.name]
        return "direct", list(value) if isinstance(value, tuple) else value
    if role.model_alias is not None and role.model_alias in profile.alias_list:
        models = list(profile.alias_list[role.model_alias])
        return "alias", models if profile.model_list_key and len(models) > 1 else models[0]
    return "inherit", None


def _explain(noun: str, what: str) -> list[str]:
    return [
        f"This {noun} is meant to {what}, but this harness",
        "may not enforce that restriction; host approvals and sandbox policy",
        "remain the only limit.",
    ]


def _commented(profile: Profile, key: str, value: Any) -> str:
    if profile.format == "toml":
        return f"# {tomlio.entry(key, value)}"
    rendered = yamlio.flow_list(list(value)) if isinstance(value, (list, tuple)) else yamlio.scalar(value)
    return f"# {key}: {rendered}"


def _readonly_value(capability: Capability) -> Any:
    return True if capability.value is None else capability.value


def _tools_value(capability: Capability, tools: tuple[str, ...]) -> Any:
    return ", ".join(tools) if capability.style == "comma" else list(tools)


def _build(role: Role, profile: Profile) -> tuple[_Document, str, str | list[str] | None]:
    doc = _Document()
    doc.add("name", role.name)
    doc.add("description", role.description)

    rule, model = resolve_model(role, profile)
    if profile.format == "hermes":
        if model is None and role.model_alias is not None:
            doc.explainer.append(f"- Model: this role's model alias `{role.model_alias}` has no Hermes mapping; "
                                 "Hermes uses the session's model.")
        elif model is None:
            doc.explainer.append("- Model: this role sets no model preference; Hermes uses the session's model.")
        else:
            shown = ", ".join(f"`{item}`" for item in ([model] if isinstance(model, str) else model))
            doc.explainer.append(f"- Model: this role prefers {shown}; Hermes uses the session's model.")
        doc.notes.append("model: explainer")
    elif model is None:
        if profile.model_inherit is not None:
            doc.add(profile.model_key, profile.model_inherit)
        if role.model_alias is not None:
            doc.notes.append(f"model: alias '{role.model_alias}' is not in this target's alias_list; inherited")
    elif isinstance(model, list):
        doc.add(profile.model_list_key, model)
    else:
        doc.add(profile.model_key, model)

    for hint, value in role.presentation.get(profile.name, {}).items():
        if hint in profile.presentation:
            doc.add(hint, value)
        else:
            doc.notes.append(f"presentation: {hint} dropped")

    noun = profile.noun
    if role.readonly:
        capability = profile.readonly
        if capability.render == "native":
            doc.add(capability.key, _readonly_value(capability))
            doc.notes.append(f"readonly: native as {capability.key}")
        elif capability.render == "commented":
            doc.comment([_commented(profile, capability.key, _readonly_value(capability))]
                        + [f"# {line}" for line in _explain(noun, "be read-only")])
            doc.notes.append("readonly: commented")
        elif capability.render == "tools":
            doc.notes.append("readonly: enforced through the tools allowlist")
        else:
            doc.explainer.append("- Read-only: do not change files, including through the shell; "
                                 "Hermes does not enforce this.")
            doc.notes.append("readonly: explainer")

    if role.tools is not None:
        capability = profile.tools
        if capability.render == "native":
            doc.add(capability.key, _tools_value(capability, role.tools))
        elif capability.render == "commented":
            doc.comment([_commented(profile, capability.key, list(role.tools))]
                        + [f"# {line}" for line in _explain(noun, "use only the listed tools")])
            doc.notes.append("tools: commented")
        else:
            doc.explainer.append("- Tools: use only " + ", ".join(role.tools) + "; Hermes does not enforce this list.")
            doc.notes.append("tools: explainer")

    if role.required_skills:
        capability = profile.required_skills
        names = list(role.required_skills)
        if capability.render == "native":
            doc.add(capability.key, names)
        elif capability.render == "commented":
            doc.comment([
                _commented(profile, capability.key, names),
                f"# This {noun} depends on the listed skills, but this harness does not",
                "# preload them; the agent is instructed to load them before starting.",
            ])
            doc.required_instruction = names
            doc.notes.append("required skills: commented and instructed")
        else:
            doc.explainer.append("- Skills: load " + ", ".join(f"`{name}`" for name in names)
                                 + " before starting work.")
            doc.notes.append("required skills: explainer")

    if role.suggested_skills:
        capability = profile.suggested_skills
        names = list(role.suggested_skills)
        if capability.render == "native":
            doc.add(capability.key, names)
        elif capability.render == "instruction":
            doc.suggested_instruction = names
            doc.notes.append("suggested skills: instructed")
        else:
            doc.explainer.append("- Suggested skills: load " + ", ".join(f"`{name}`" for name in names)
                                 + " when the task makes them relevant.")
            doc.notes.append("suggested skills: explainer")

    for key in sorted(role.overrides.get(profile.name, {})):
        doc.add(key, role.overrides[profile.name][key])

    return doc, rule, model


def _skills_section(required: list[str], suggested: list[str]) -> list[str]:
    lines = [SKILLS_HEADING, ""]
    if required:
        lines.append("This harness does not preload skills, so load each of these before starting work:")
        lines.append("")
        lines.extend(f"- `{name}`" for name in required)
        lines.append("")
    if suggested:
        lines.append("Load each of these when the task makes it relevant:")
        lines.append("")
        lines.extend(f"- `{name}`" for name in suggested)
        lines.append("")
    return lines


def insert_skills_section(body: str, required: list[str], suggested: list[str]) -> str:
    """Insert the skill instruction section before the body's second H2, or at its end."""
    if not required and not suggested:
        return body
    lines = body.rstrip("\n").split("\n")
    if any(line.strip() == SKILLS_HEADING for line in lines):
        raise GenerationError(f"body already has a '{SKILLS_HEADING}' heading")
    in_fence = False
    seen = 0
    for index, line in enumerate(lines):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and _H2.match(line):
            seen += 1
            if seen == 2:
                return "\n".join(lines[:index] + _skills_section(required, suggested) + lines[index:]) + "\n"
    return "\n".join(lines + [""] + _skills_section(required, suggested)).rstrip("\n") + "\n"


def _frontmatter(doc: _Document, fmt: str) -> list[str]:
    lines: list[str] = []
    for kind, index in doc.order:
        if kind == "comment":
            lines.extend(doc.comments[index])
            continue
        key, value = doc.entries[index]
        if fmt == "toml":
            lines.append(tomlio.entry(key, value))
        else:
            lines.extend(yamlio.entry(key, value))
    return lines


def _template_env(root: Path) -> ImmutableSandboxedEnvironment:
    templates = root / SOURCES_DIR / "templates"
    for path in [root / SOURCES_DIR, templates, *sorted(templates.iterdir())]:
        if path.is_symlink():
            raise GenerationError(f"{path.relative_to(root).as_posix()}: templates may not be symlinks")
    env = ImmutableSandboxedEnvironment(
        loader=FileSystemLoader(str(templates), followlinks=False),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    env.globals.clear()
    env.filters.clear()
    env.tests.clear()
    return env


def _render_template(env: ImmutableSandboxedEnvironment, profile: Profile, context: dict[str, str]) -> str:
    try:
        text = env.get_template(profile.template).render(**context)
    except TemplateError as error:
        raise GenerationError(f"{SOURCES_DIR}/templates/{profile.template}: {error}") from error
    if not text.endswith("\n") or text.endswith("\n\n") or "\r" in text:
        raise GenerationError(f"{SOURCES_DIR}/templates/{profile.template}: output must end with exactly one newline")
    return text


def _allowed_keys(profile: Profile) -> set[str]:
    keys = {"name", "description", *profile.presentation, *profile.overrides}
    keys.update(key for key in (profile.model_key, profile.model_list_key) if key)
    for capability in (profile.readonly, profile.tools, profile.required_skills, profile.suggested_skills):
        if capability.render == "native":
            keys.add(capability.key)
    if profile.format == "toml":
        keys.add("developer_instructions")
    return keys


def _check_markdown(text: str, expected: dict[str, Any], body: str, label: str) -> None:
    if not text.startswith("---\n"):
        raise GenerationError(f"{label}: rendered file does not open with frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise GenerationError(f"{label}: rendered frontmatter is not closed")
    parsed = yamlio.loads(text[4 : end + 1])
    if parsed != expected:
        raise GenerationError(f"{label}: rendered frontmatter does not read back as the intended fields")
    if text[end + 5 :] != body:
        raise GenerationError(f"{label}: rendered body differs from the role body")


def render_role(env: ImmutableSandboxedEnvironment, role: Role, profile: Profile) -> Rendered:
    """Render one role for one target and verify the result reads back as intended."""
    label = f"{role.name} ({profile.name})"
    doc, rule, model = _build(role, profile)
    allowed = _allowed_keys(profile)
    unexpected = [key for key, _ in doc.entries if key not in allowed]
    if unexpected:
        raise GenerationError(f"{label}: would emit field(s) the profile does not allow: {', '.join(unexpected)}")

    if profile.format == "hermes":
        prompt = role.body
        if doc.explainer:
            prompt = "\n".join([f"Harness notes for this personality, generated from the `{role.name}` role:", "",
                                *doc.explainer, "", prompt])
        description_line = "description: " + json.dumps(role.description, ensure_ascii=False)
        prompt_line = "system_prompt: " + json.dumps(prompt, ensure_ascii=False)
        text = _render_template(env, profile, {"name": role.name, "document": f"{description_line}\n{prompt_line}"})
        expected = {"description": role.description, "system_prompt": prompt}
        if yamlio.loads(text) != expected or text != f"{description_line}\n{prompt_line}\n":
            raise GenerationError(f"{label}: rendered personality does not read back as intended")
    else:
        body = insert_skills_section(role.body, doc.required_instruction, doc.suggested_instruction)
        if profile.format == "toml":
            lines = _frontmatter(doc, "toml") + [tomlio.entry("developer_instructions", body, multiline=True)]
            text = _render_template(env, profile, {"name": role.name, "document": "\n".join(lines)})
            expected = {**doc.native(), "developer_instructions": body}
            try:
                parsed = tomllib.loads(text)
            except tomllib.TOMLDecodeError as error:
                raise GenerationError(f"{label}: rendered TOML does not parse: {error}") from error
            if parsed != expected:
                raise GenerationError(f"{label}: rendered TOML does not read back as the intended fields")
        else:
            frontmatter = "\n".join(_frontmatter(doc, "markdown"))
            text = _render_template(env, profile, {"name": role.name, "frontmatter": frontmatter,
                                                   "body": body.rstrip("\n")})
            _check_markdown(text, doc.native(), body, label)

    return Rendered(
        role=role.name,
        target=profile.name,
        path=profile.output_path(role.name),
        content=text.encode("utf-8"),
        model_rule=rule,
        model_value=model,
        notes=doc.notes,
    )


def render_all(root: Path, profiles: dict[str, Profile], roles: dict[str, Role]) -> list[Rendered]:
    """Render every role for every target it lists, in a stable order."""
    env = _template_env(root)
    rendered: list[Rendered] = []
    problems: list[str] = []
    for name in sorted(roles):
        role = roles[name]
        for target in sorted(role.targets):
            try:
                rendered.append(render_role(env, role, profiles[target]))
            except GenerationError as error:
                problems.extend(error.problems)
    if problems:
        raise GenerationError(problems)
    return rendered
