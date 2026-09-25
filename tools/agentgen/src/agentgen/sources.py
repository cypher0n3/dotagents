"""Load and validate target profiles and role sources.

Every key at every level is checked against the schema below, so an unknown or
misspelled key fails generation instead of being ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from agentgen import yamlio
from agentgen.errors import GenerationError

SCHEMA_VERSION = 1
SOURCES_DIR = "agent_sources"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TEMPLATE_PATTERN = re.compile(r"^[a-z0-9-]+\.[a-z]+\.j2$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
RESERVED_NAMES = ("readme",)

# Claude Code tool names a role may list; the Claude target is the only one that
# enforces the list, and every other target receives it as a comment.
KNOWN_TOOLS = (
    "Agent",
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "Skill",
    "Task",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
)
WRITE_TOOLS = ("Edit", "NotebookEdit", "Write")
CLAUDE_COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")

FORMATS = {"markdown": ".md", "toml": ".toml", "hermes": ".yaml"}
OUTPUT_ROOTS = ("agents", "generated")
READONLY_RENDERS = ("native", "commented", "tools", "explainer")
TOOLS_RENDERS = ("native", "commented", "explainer")
REQUIRED_SKILL_RENDERS = ("native", "commented", "explainer")
SUGGESTED_SKILL_RENDERS = ("native", "instruction", "explainer")
TOOL_STYLES = ("comma", "list")
OVERRIDE_TYPES = ("enum", "string", "integer", "boolean")
# Shared role fields an override may never replace.
PROTECTED_FIELDS = ("name", "description", "body", "targets", "skills", "restrictions", "model", "presentation")


def _require_mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise GenerationError(f"{label}: must be a mapping")
    return value


def _check_keys(value: dict, label: str, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> None:
    problems = [f"{label}: missing required key '{key}'" for key in required if key not in value]
    allowed = set(required) | set(optional)
    problems += [f"{label}: unknown key '{key}'" for key in value if key not in allowed]
    if problems:
        raise GenerationError(problems)


def _string(value: Any, label: str, *, multiline: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GenerationError(f"{label}: must be a non-empty string")
    yamlio.check_text(value, label, multiline=multiline)
    return value


def _optional_string(value: Any, label: str) -> str | None:
    return None if value is None else _string(value, label)


def _string_list(value: Any, label: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise GenerationError(f"{label}: must be a list of non-empty strings")
    if not value and not allow_empty:
        raise GenerationError(f"{label}: must not be empty")
    if len(set(value)) != len(value):
        raise GenerationError(f"{label}: lists an entry more than once")
    for index, item in enumerate(value):
        yamlio.check_text(item, f"{label}[{index}]")
    return tuple(value)


def _schema(value: dict, label: str) -> None:
    version = value.get("schema")
    if version != SCHEMA_VERSION or isinstance(version, bool):
        raise GenerationError(f"{label}: unsupported schema {version!r}; this generator reads schema {SCHEMA_VERSION}")


def _name(value: Any, label: str, stem: str) -> str:
    name = _string(value, f"{label}: name")
    if not NAME_PATTERN.match(name) or len(name) > MAX_NAME_LENGTH:
        raise GenerationError(f"{label}: name '{name}' must be lowercase kebab-case, at most {MAX_NAME_LENGTH} characters")
    if name != stem:
        raise GenerationError(f"{label}: name '{name}' must match the file name '{stem}'")
    if name in RESERVED_NAMES:
        raise GenerationError(f"{label}: name '{name}' is reserved")
    return name


@dataclass(frozen=True)
class Capability:
    """How one target renders one piece of shared role intent."""

    render: str
    key: str | None = None
    value: Any = None
    style: str | None = None


@dataclass(frozen=True)
class Override:
    """One native setting a role may set for this target."""

    type: str
    values: tuple[str, ...] = ()
    minimum: int | None = None


@dataclass(frozen=True)
class Profile:
    """A target profile from agent_sources/targets/<name>.yaml."""

    name: str
    path: str
    text: str
    application: dict
    format: str
    template: str
    output: str
    extension: str
    noun: str
    model_key: str | None
    model_list_key: str | None
    model_inherit: str | None
    alias_list: dict[str, tuple[str, ...]]
    readonly: Capability
    tools: Capability
    required_skills: Capability
    suggested_skills: Capability
    presentation: tuple[str, ...]
    overrides: dict[str, Override]

    def output_path(self, role: str) -> str:
        return f"{self.output}/{role}{self.extension}"


def _capability(value: Any, label: str, renders: tuple[str, ...], *, with_value: bool = False,
                with_style: bool = False) -> Capability:
    mapping = _require_mapping(value, label)
    optional = ("key",) + (("value",) if with_value else ()) + (("style",) if with_style else ())
    _check_keys(mapping, label, ("render",), optional)
    render = mapping["render"]
    if render not in renders:
        raise GenerationError(f"{label}: render must be one of {', '.join(renders)}")
    key = _optional_string(mapping.get("key"), f"{label}: key")
    if render in ("native", "commented") and key is None:
        raise GenerationError(f"{label}: a {render} rendering needs a key")
    if key is not None and not yamlio.KEY_PATTERN.match(key):
        raise GenerationError(f"{label}: key '{key}' is not a valid field name")
    style = mapping.get("style")
    if with_style and style is not None and style not in TOOL_STYLES:
        raise GenerationError(f"{label}: style must be one of {', '.join(TOOL_STYLES)}")
    item = mapping.get("value")
    if item is not None and not isinstance(item, (str, bool)):
        raise GenerationError(f"{label}: value must be a string or boolean")
    return Capability(render=render, key=key, value=item, style=style)


def _override(value: Any, label: str) -> Override:
    mapping = _require_mapping(value, label)
    _check_keys(mapping, label, ("type",), ("values", "minimum"))
    kind = mapping["type"]
    if kind not in OVERRIDE_TYPES:
        raise GenerationError(f"{label}: type must be one of {', '.join(OVERRIDE_TYPES)}")
    values = _string_list(mapping.get("values", []), f"{label}: values")
    if kind == "enum" and not values:
        raise GenerationError(f"{label}: an enum override needs values")
    minimum = mapping.get("minimum")
    if minimum is not None and (kind != "integer" or not isinstance(minimum, int) or isinstance(minimum, bool)):
        raise GenerationError(f"{label}: minimum applies only to an integer override")
    return Override(type=kind, values=values, minimum=minimum)


def load_profile(root: Path, path: Path) -> Profile:
    """Load and validate one target profile."""
    label = path.relative_to(root).as_posix()
    text = yamlio.read_text(path, label)
    data = _require_mapping(yamlio.parse(text, label), label)
    _check_keys(
        data,
        label,
        ("schema", "name", "application", "format", "template", "output", "noun", "model", "readonly", "tools",
         "required_skills", "suggested_skills"),
        ("alias_list", "presentation", "overrides"),
    )
    _schema(data, label)
    name = _name(data["name"], label, path.stem)

    application = _require_mapping(data["application"], f"{label}: application")
    _check_keys(application, f"{label}: application", ("name", "checked", "evidence"), ("notes",))
    _string(application["name"], f"{label}: application.name")
    _string(application["checked"], f"{label}: application.checked")
    _string_list(application["evidence"], f"{label}: application.evidence", allow_empty=False)
    if "notes" in application:
        _string_list(application["notes"], f"{label}: application.notes")

    fmt = data["format"]
    if fmt not in FORMATS:
        raise GenerationError(f"{label}: format must be one of {', '.join(FORMATS)}")
    template = _string(data["template"], f"{label}: template")
    if not TEMPLATE_PATTERN.match(template):
        raise GenerationError(f"{label}: template '{template}' must be a plain file name ending in .j2")
    template_path = root / SOURCES_DIR / "templates" / template
    if template_path.is_symlink() or not template_path.is_file():
        raise GenerationError(f"{label}: template '{template}' is not a regular file under {SOURCES_DIR}/templates")

    output = _string(data["output"], f"{label}: output")
    pure = PurePosixPath(output)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != output or pure.parts[0] not in OUTPUT_ROOTS:
        raise GenerationError(f"{label}: output '{output}' must be a relative path under {' or '.join(OUTPUT_ROOTS)}/")
    if pure.parts[0] == "agents" and output != "agents":
        raise GenerationError(f"{label}: output under agents/ must be agents itself")

    noun = data["noun"]
    if noun not in ("agent", "persona", "personality"):
        raise GenerationError(f"{label}: noun must be agent, persona, or personality")

    model = _require_mapping(data["model"], f"{label}: model")
    _check_keys(model, f"{label}: model", (), ("key", "list_key", "inherit"))
    model_key = _optional_string(model.get("key"), f"{label}: model.key")
    list_key = _optional_string(model.get("list_key"), f"{label}: model.list_key")
    inherit = _optional_string(model.get("inherit"), f"{label}: model.inherit")
    if inherit is not None and model_key is None:
        raise GenerationError(f"{label}: model.inherit needs model.key")

    aliases: dict[str, tuple[str, ...]] = {}
    for alias, models in _require_mapping(data.get("alias_list") or {}, f"{label}: alias_list").items():
        if not NAME_PATTERN.match(alias):
            raise GenerationError(f"{label}: alias '{alias}' must be lowercase kebab-case")
        aliases[alias] = _string_list(models, f"{label}: alias_list.{alias}", allow_empty=False)

    readonly = _capability(data["readonly"], f"{label}: readonly", READONLY_RENDERS, with_value=True)
    tools = _capability(data["tools"], f"{label}: tools", TOOLS_RENDERS, with_style=True)
    required = _capability(data["required_skills"], f"{label}: required_skills", REQUIRED_SKILL_RENDERS)
    suggested = _capability(data["suggested_skills"], f"{label}: suggested_skills", SUGGESTED_SKILL_RENDERS)
    if readonly.render == "tools" and tools.render != "native":
        raise GenerationError(f"{label}: readonly can be carried by tools only when tools render natively")
    capabilities = (readonly, tools, required, suggested)
    if fmt == "hermes":
        if model_key is not None or any(item.render not in ("explainer",) for item in capabilities):
            raise GenerationError(f"{label}: a hermes profile renders model, restrictions, and skills as explainer text")
    elif any(item.render == "explainer" for item in capabilities):
        raise GenerationError(f"{label}: only a hermes profile uses explainer renderings")

    presentation = _string_list(data.get("presentation") or [], f"{label}: presentation")
    overrides = {
        key: _override(item, f"{label}: overrides.{key}")
        for key, item in _require_mapping(data.get("overrides") or {}, f"{label}: overrides").items()
    }
    reserved = {"name", "description", "developer_instructions", model_key, list_key, readonly.key, tools.key,
                required.key, suggested.key, *presentation}
    for key in overrides:
        if key in PROTECTED_FIELDS or key in reserved or not yamlio.KEY_PATTERN.match(key):
            raise GenerationError(f"{label}: override '{key}' collides with a shared or reserved field")

    return Profile(
        name=name,
        path=label,
        text=text,
        application=application,
        format=fmt,
        template=template,
        output=output,
        extension=FORMATS[fmt],
        noun=noun,
        model_key=model_key,
        model_list_key=list_key,
        model_inherit=inherit,
        alias_list=aliases,
        readonly=readonly,
        tools=tools,
        required_skills=required,
        suggested_skills=suggested,
        presentation=presentation,
        overrides=overrides,
    )


@dataclass(frozen=True)
class Role:
    """A role from agent_sources/roles/<name>.yaml with its Markdown body."""

    name: str
    path: str
    text: str
    description: str
    body_path: str
    body: str
    targets: tuple[str, ...]
    model_alias: str | None
    model_direct: dict[str, str | tuple[str, ...]]
    required_skills: tuple[str, ...]
    suggested_skills: tuple[str, ...]
    readonly: bool
    tools: tuple[str, ...] | None
    presentation: dict[str, dict[str, str]] = field(default_factory=dict)
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


def _body(root: Path, value: Any, label: str) -> tuple[str, str]:
    relative = _string(value, f"{label}: body")
    pure = PurePosixPath(relative)
    if (pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative or pure.parts[0] != "prompts"
            or pure.suffix != ".md"):
        raise GenerationError(f"{label}: body '{relative}' must be a Markdown file under prompts/")
    base = root / SOURCES_DIR
    path = base / relative
    current = base
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise GenerationError(f"{label}: body '{relative}' passes through a symlink")
    if not path.is_file():
        raise GenerationError(f"{label}: body '{relative}' does not exist")
    text = yamlio.read_text(path, f"{SOURCES_DIR}/{relative}")
    for index, line in enumerate(text.split("\n"), start=1):
        yamlio.check_text(line, f"{SOURCES_DIR}/{relative}:{index}")
    if not text.startswith("# "):
        raise GenerationError(f"{SOURCES_DIR}/{relative}: must open with an H1 heading")
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise GenerationError(f"{SOURCES_DIR}/{relative}: must end with exactly one newline")
    return relative, text


def load_role(root: Path, path: Path, profiles: dict[str, Profile], skills_dir: Path) -> Role:
    """Load and validate one role source against the loaded target profiles."""
    label = path.relative_to(root).as_posix()
    text = yamlio.read_text(path, label)
    data = _require_mapping(yamlio.parse(text, label), label)
    _check_keys(data, label, ("schema", "name", "description", "body", "targets"),
                ("model", "skills", "restrictions", "presentation", "overrides"))
    _schema(data, label)
    name = _name(data["name"], label, path.stem)
    description = _string(data["description"], f"{label}: description")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise GenerationError(f"{label}: description exceeds {MAX_DESCRIPTION_LENGTH} characters")
    body_path, body = _body(root, data["body"], label)

    targets = _string_list(data["targets"], f"{label}: targets", allow_empty=False)
    unknown = [target for target in targets if target not in profiles]
    if unknown:
        raise GenerationError(f"{label}: unknown target(s) {', '.join(unknown)}")

    alias: str | None = None
    direct: dict[str, str | tuple[str, ...]] = {}
    for key, item in _require_mapping(data.get("model") or {}, f"{label}: model").items():
        if key == "alias":
            alias = _string(item, f"{label}: model.alias")
            if not NAME_PATTERN.match(alias):
                raise GenerationError(f"{label}: model.alias '{alias}' must be lowercase kebab-case")
            continue
        if key not in targets:
            raise GenerationError(f"{label}: model.{key} names a target the role does not list")
        if isinstance(item, list):
            if profiles[key].model_list_key is None:
                raise GenerationError(f"{label}: model.{key} is a list, but target {key} takes one model")
            direct[key] = _string_list(item, f"{label}: model.{key}", allow_empty=False)
        else:
            direct[key] = _string(item, f"{label}: model.{key}")
    if alias is not None and not any(alias in profile.alias_list for profile in profiles.values()):
        raise GenerationError(f"{label}: model alias '{alias}' is not defined by any target profile")

    skills = _require_mapping(data.get("skills") or {}, f"{label}: skills")
    _check_keys(skills, f"{label}: skills", (), ("required", "suggested"))
    required = _string_list(skills.get("required", []), f"{label}: skills.required")
    suggested = _string_list(skills.get("suggested", []), f"{label}: skills.suggested")
    overlap = sorted(set(required) & set(suggested))
    if overlap:
        raise GenerationError(f"{label}: skill(s) {', '.join(overlap)} are both required and suggested")
    malformed = [skill for skill in required + suggested if not NAME_PATTERN.match(skill)]
    if malformed:
        raise GenerationError(f"{label}: skill name(s) {', '.join(malformed)} are not lowercase kebab-case")
    missing = [skill for skill in required + suggested if not (skills_dir / skill / "SKILL.md").is_file()]
    if missing:
        raise GenerationError(f"{label}: skill(s) not found under skills/: {', '.join(missing)}")

    restrictions = _require_mapping(data.get("restrictions") or {}, f"{label}: restrictions")
    _check_keys(restrictions, f"{label}: restrictions", (), ("readonly", "tools"))
    readonly = restrictions.get("readonly", False)
    if not isinstance(readonly, bool):
        raise GenerationError(f"{label}: restrictions.readonly must be true or false")
    tools = None
    if "tools" in restrictions:
        tools = _string_list(restrictions["tools"], f"{label}: restrictions.tools", allow_empty=False)
        unknown_tools = [tool for tool in tools if tool not in KNOWN_TOOLS]
        if unknown_tools:
            raise GenerationError(f"{label}: unknown tool(s) {', '.join(unknown_tools)}; known: {', '.join(KNOWN_TOOLS)}")
    if readonly and tools is not None:
        writers = [tool for tool in tools if tool in WRITE_TOOLS]
        if writers:
            raise GenerationError(f"{label}: a read-only role cannot list {', '.join(writers)}")
    for target in targets:
        if readonly and profiles[target].readonly.render == "tools" and tools is None:
            raise GenerationError(f"{label}: target {target} enforces read-only only through tools, so list them")

    presentation: dict[str, dict[str, str]] = {}
    for target, hints in _require_mapping(data.get("presentation") or {}, f"{label}: presentation").items():
        if target not in targets:
            raise GenerationError(f"{label}: presentation.{target} names a target the role does not list")
        hints = _require_mapping(hints, f"{label}: presentation.{target}")
        presentation[target] = {
            hint: _string(item, f"{label}: presentation.{target}.{hint}") for hint, item in hints.items()
        }
    if "claude" in targets:
        color = presentation.get("claude", {}).get("color")
        if color not in CLAUDE_COLORS:
            raise GenerationError(f"{label}: presentation.claude.color is required and must be one of "
                                  f"{', '.join(CLAUDE_COLORS)}")

    overrides: dict[str, dict[str, Any]] = {}
    for target, settings in _require_mapping(data.get("overrides") or {}, f"{label}: overrides").items():
        if target not in targets:
            raise GenerationError(f"{label}: overrides.{target} names a target the role does not list")
        settings = _require_mapping(settings, f"{label}: overrides.{target}")
        allowed = profiles[target].overrides
        for key, item in settings.items():
            where = f"{label}: overrides.{target}.{key}"
            if key in PROTECTED_FIELDS:
                raise GenerationError(f"{where}: an override cannot change the shared role field '{key}'")
            if key not in allowed:
                raise GenerationError(f"{where}: target {target} does not allow this override")
            _check_override(item, allowed[key], where)
        overrides[target] = dict(settings)

    return Role(
        name=name,
        path=label,
        text=text,
        description=description,
        body_path=body_path,
        body=body,
        targets=targets,
        model_alias=alias,
        model_direct=direct,
        required_skills=required,
        suggested_skills=suggested,
        readonly=readonly,
        tools=tools,
        presentation=presentation,
        overrides=overrides,
    )


def _check_override(item: Any, spec: Override, where: str) -> None:
    if spec.type == "enum":
        if item not in spec.values:
            raise GenerationError(f"{where}: must be one of {', '.join(spec.values)}")
    elif spec.type == "string":
        _string(item, where)
    elif spec.type == "boolean":
        if not isinstance(item, bool):
            raise GenerationError(f"{where}: must be true or false")
    elif not isinstance(item, int) or isinstance(item, bool) or (spec.minimum is not None and item < spec.minimum):
        raise GenerationError(f"{where}: must be an integer" + (f" of at least {spec.minimum}" if spec.minimum else ""))


def _yaml_files(directory: Path, label: str) -> list[Path]:
    if not directory.is_dir():
        raise GenerationError(f"{label}: directory not found")
    files = sorted(directory.iterdir())
    problems = [f"{label}/{path.name}: not a .yaml file" for path in files if path.suffix != ".yaml"]
    problems += [f"{label}/{path.name}: must be a regular file, not a symlink" for path in files
                 if path.suffix == ".yaml" and (path.is_symlink() or not path.is_file())]
    if problems:
        raise GenerationError(problems)
    return files


@dataclass(frozen=True)
class Sources:
    """Every profile and role, validated together."""

    profiles: dict[str, Profile]
    roles: dict[str, Role]


def load_sources(root: Path) -> Sources:
    """Load every profile and role under agent_sources/, collecting all problems."""
    base = root / SOURCES_DIR
    problems: list[str] = []
    profiles: dict[str, Profile] = {}
    for path in _yaml_files(base / "targets", f"{SOURCES_DIR}/targets"):
        try:
            profiles[path.stem] = load_profile(root, path)
        except GenerationError as error:
            problems.extend(error.problems)
    if problems:
        raise GenerationError(problems)
    roles: dict[str, Role] = {}
    for path in _yaml_files(base / "roles", f"{SOURCES_DIR}/roles"):
        try:
            roles[path.stem] = load_role(root, path, profiles, root / "skills")
        except GenerationError as error:
            problems.extend(error.problems)
    if problems:
        raise GenerationError(problems)
    if not roles:
        raise GenerationError(f"{SOURCES_DIR}/roles: no roles found")
    return Sources(profiles=profiles, roles=roles)
