"""Rutas protegidas (spec goal-loop): una rama no puede modificar, borrar ni renombrar archivos
existentes protegidos, aunque sí crear archivos nuevos en esas rutas.

Los archivos críticos del harness (lo que define cómo se juzga una rama, y los sub-agentes y
skills de Claude Code de `.claude/agents/` y `.claude/skills/`, como el equipo ideal) están
siempre protegidos y ningún objetivo ni configuración puede liberarlos.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from factory.globs import matches

STATIC_CRITICAL = (
    "feature_list.json",
    "factory.toml",
    "prompts/**",
    ".claude/agents/**",
    ".claude/skills/**",
)
# Rutas de ejemplo para detectar un `allow_modify` que liberaría algún crítico estático.
CRITICAL_SAMPLES = (
    "feature_list.json",
    "factory.toml",
    "prompts/maker.md",
    "prompts/x/y.md",
    ".claude/agents/x.md",
    ".claude/skills/x/SKILL.md",
)
SHELLS = ("bash", "sh", "zsh")
# Estados de `git diff --name-status` que alteran un archivo existente. Las altas (A) y las
# copias (C, el original no cambia) no cuentan.
ALTERING = {"M": "modificado", "D": "borrado", "T": "cambio de tipo", "R": "renombrado"}


def releases_critical(pattern: str) -> bool:
    """¿Liberaría `pattern` algún crítico estático? Lo detecta tanto si el patrón cubre una
    muestra (`**`, `.claude/**`) como si, leído como ruta, cae dentro de un crítico
    (`.claude/agents/qa.md`, `prompts/checker.md`)."""
    if any(matches(sample, [pattern]) for sample in CRITICAL_SAMPLES):
        return True
    return matches(pattern, list(STATIC_CRITICAL))


def script_path(command: str, root: Path) -> str | None:
    """Ruta relativa del script que ejecuta `command`, si es un archivo del repo."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if tokens and tokens[0] in SHELLS and len(tokens) > 1:
        tokens = tokens[1:]
    if not tokens or "/" not in tokens[0] or tokens[0].startswith("/"):
        return None
    relative = tokens[0].removeprefix("./")
    return relative if (root / relative).is_file() else None


@dataclass
class Protection:
    critical: list[str]
    protected: list[str] = field(default_factory=list)
    released: list[str] = field(default_factory=list)

    def is_protected(self, path: str) -> bool:
        if matches(path, self.critical):
            return True
        return matches(path, self.protected) and not matches(path, self.released)

    def describe(self) -> list[str]:
        return [
            f"Rutas protegidas (críticas, siempre): {', '.join(self.critical)}",
            f"Rutas protegidas (configuración/objetivo): {', '.join(self.protected) or '—'}",
            f"Liberadas por el objetivo: {', '.join(self.released) or '—'}",
        ]


def effective(
    root: Path,
    config_paths: Iterable[str],
    goal_protected: Iterable[str],
    goal_released: Iterable[str],
    commands: Iterable[str],
) -> Protection:
    critical = list(STATIC_CRITICAL)
    for command in commands:
        script = script_path(command, root)
        if script and script not in critical:
            critical.append(script)
    protected = list(dict.fromkeys([*config_paths, *goal_protected]))
    return Protection(critical, protected, list(goal_released))


@dataclass(frozen=True)
class Violation:
    path: str
    change: str

    def __str__(self) -> str:
        return f"{self.path} ({self.change})"


def violations(entries: Iterable[tuple[str, str, str | None]], protection: Protection) -> list:
    """Cambios de `git diff --name-status` (estado, ruta, ruta nueva) que tocan archivos
    existentes protegidos. En un renombrado se evalúa la ruta original."""
    found = []
    for status, path, _new in entries:
        change = ALTERING.get(status[:1])
        if change and protection.is_protected(path):
            found.append(Violation(path, change))
    return found
