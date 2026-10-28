"""Objetivos (`goal.md`): metadatos verificables en frontmatter YAML + metodología en Markdown.

Un objetivo sin al menos un criterio ejecutable no se acepta: el loop necesita una condición de
éxito comprobable por máquina (L13: objetivo + verificación + condición de parada).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from factory.config import (
    ConfigError,
    LoopConfig,
    RoleConfig,
    apply_values,
    check_permission_mode,
    enforce_role_policy,
)

MODES = ("finite", "monitor")
PROTECTED_PATHS = ("feature_list.json",)
STOP_KEYS = (
    "max_rounds",
    "max_budget_usd",
    "no_progress_rounds",
    "consecutive_passes",
    "round_timeout_min",
)
ROLE_OVERRIDES = ("model", "permission_mode", "allowed_tools", "denied_tools")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)(.*)\Z", re.DOTALL)


class GoalError(ValueError):
    pass


@dataclass(frozen=True)
class Criterion:
    name: str
    run: str


@dataclass
class StopConditions:
    max_rounds: int
    max_budget_usd: float
    no_progress_rounds: int
    consecutive_passes: int
    round_timeout_min: float


@dataclass
class Goal:
    id: str
    objective: str
    mode: str
    acceptance: list[Criterion]
    allow: list[str]
    deny: list[str]
    stop: StopConditions
    body: str
    path: Path | None = None
    feature: str | None = None
    roles: dict[str, dict] = field(default_factory=dict)
    defaults_applied: list[str] = field(default_factory=list)
    raw: str = ""

    def role(self, name: str, base: RoleConfig) -> RoleConfig:
        """Rol efectivo: factory.toml + overrides del objetivo + políticas obligatorias."""
        merged = RoleConfig(**{f.name: getattr(base, f.name) for f in fields(base)})
        apply_values(merged, self.roles.get(name, {}), f"roles.{name}")
        return enforce_role_policy(name, merged)

    def describe(self) -> str:
        lines = [
            f"Objetivo '{self.id}' ({self.mode}): {self.objective}",
            "Criterios de aceptación:",
            *(f"  - {c.name}: {c.run}" for c in self.acceptance),
            f"Alcance permitido: {', '.join(self.allow)}",
            f"Alcance prohibido: {', '.join(self.deny)}",
            "Límites efectivos:",
        ]
        for key in STOP_KEYS:
            origin = " (por defecto)" if key in self.defaults_applied else ""
            lines.append(f"  - {key} = {getattr(self.stop, key)}{origin}")
        if self.feature:
            lines.append(f"Feature asociada: {self.feature}")
        return "\n".join(lines)


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Glob con `**` (cualquier profundidad), `*` y `?` (sin cruzar `/`). Anclado a la raíz."""
    pattern = pattern.strip().removeprefix("./")
    if pattern.endswith("/"):
        pattern += "**"
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, patterns: list[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)


def out_of_scope(paths: list[str], goal: Goal) -> list[str]:
    """Archivos fuera del alcance: no permitidos o explícitamente prohibidos."""
    return [p for p in paths if matches(p, goal.deny) or not matches(p, goal.allow)]


def _str_list(value: object, where: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise GoalError(f"{where} debe ser una lista de rutas o globs")
    return list(value)


def _criteria(value: object) -> list[Criterion]:
    if not isinstance(value, list) or not value:
        raise GoalError(
            "Faltan criterios de aceptación: declara `acceptance` con al menos un criterio "
            "verificable por máquina (`run: <comando>`)."
        )
    criteria = []
    for index, item in enumerate(value, 1):
        if isinstance(item, str):
            item = {"run": item}
        if not isinstance(item, dict):
            raise GoalError(f"acceptance[{index}] debe ser un objeto con `run`")
        run = item.get("run")
        if run is not None and (not isinstance(run, str) or not run.strip()):
            raise GoalError(f"acceptance[{index}].run debe ser un comando no vacío")
        name = str(item.get("name") or f"criterio-{index}")
        if run:
            criteria.append(Criterion(name, run.strip()))
    if not criteria:
        raise GoalError(
            "Ningún criterio de aceptación es verificable por máquina: cada criterio necesita "
            "`run: <comando>` que termine en 0 cuando se cumple. El loop no se inicia."
        )
    names = [c.name for c in criteria]
    if len(names) != len(set(names)):
        raise GoalError("Los nombres de los criterios de aceptación deben ser únicos")
    return criteria


def _stop(value: object, defaults: LoopConfig) -> tuple[StopConditions, list[str]]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise GoalError("`stop` debe ser un objeto")
    unknown = set(value) - set(STOP_KEYS)
    if unknown:
        raise GoalError(f"Claves desconocidas en `stop`: {', '.join(sorted(unknown))}")
    values, applied = {}, []
    for key in STOP_KEYS:
        if key in value:
            number = value[key]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or number <= 0:
                raise GoalError(f"stop.{key} debe ser un número mayor que 0")
            values[key] = number
        else:
            values[key] = getattr(defaults, key)
            applied.append(key)
    for key in ("max_rounds", "no_progress_rounds", "consecutive_passes"):
        if not float(values[key]).is_integer():
            raise GoalError(f"stop.{key} debe ser entero")
        values[key] = int(values[key])
    return StopConditions(**values), applied


def _roles(value: object) -> dict[str, dict]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise GoalError("`roles` debe ser un objeto")
    for name, overrides in value.items():
        if name not in ("maker", "checker") or not isinstance(overrides, dict):
            raise GoalError(f"roles.{name}: rol desconocido o mal formado")
        unknown = set(overrides) - set(ROLE_OVERRIDES)
        if unknown:
            raise GoalError(f"roles.{name}: claves no permitidas {sorted(unknown)}")
        if "permission_mode" in overrides:
            try:
                check_permission_mode(overrides["permission_mode"], f"roles.{name}")
            except ConfigError as exc:
                raise GoalError(str(exc)) from exc
    return value


def parse_goal_text(text: str, defaults: LoopConfig, path: Path | None = None) -> Goal:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise GoalError("goal.md debe empezar con un frontmatter YAML entre líneas `---`")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise GoalError(f"Frontmatter YAML inválido: {exc}") from exc
    if not isinstance(meta, dict):
        raise GoalError("El frontmatter debe ser un objeto YAML")
    known = {"id", "objective", "mode", "feature", "acceptance", "scope", "stop", "roles"}
    unknown = set(meta) - known
    if unknown:
        raise GoalError(f"Claves desconocidas en el frontmatter: {', '.join(sorted(unknown))}")

    goal_id = str(meta.get("id") or (path.stem if path else "")).strip()
    if not ID_RE.match(goal_id):
        raise GoalError(f"id '{goal_id}' inválido: usa minúsculas, dígitos y guiones")
    objective = meta.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise GoalError("Falta `objective`: describe el objetivo en una frase")
    mode = meta.get("mode", "finite")
    if mode not in MODES:
        raise GoalError(f"mode '{mode}' inválido; usa {' o '.join(MODES)}")
    feature = meta.get("feature")
    if feature is not None and not isinstance(feature, str):
        raise GoalError("`feature` debe ser el id de una feature")

    scope = meta.get("scope") or {}
    if not isinstance(scope, dict):
        raise GoalError("`scope` debe ser un objeto con `allow` y `deny`")
    allow = _str_list(scope.get("allow"), "scope.allow") or ["**"]
    deny = _str_list(scope.get("deny"), "scope.deny")
    deny += [p for p in PROTECTED_PATHS if p not in deny]

    stop, applied = _stop(meta.get("stop"), defaults)
    return Goal(
        id=goal_id,
        objective=objective.strip(),
        mode=mode,
        acceptance=_criteria(meta.get("acceptance")),
        allow=allow,
        deny=deny,
        stop=stop,
        body=match.group(2).strip(),
        path=path,
        feature=feature,
        roles=_roles(meta.get("roles")),
        defaults_applied=applied,
        raw=text,
    )


def load_goal(path: Path, defaults: LoopConfig) -> Goal:
    if not path.exists():
        raise GoalError(f"No existe el objetivo: {path}")
    return parse_goal_text(path.read_text(encoding="utf-8"), defaults, path)
