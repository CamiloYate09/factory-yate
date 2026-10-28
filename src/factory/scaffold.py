"""`factory init`: genera el harness mínimo en un repositorio destino (spec harness-scaffolding).

Nunca sobrescribe ni borra un archivo existente sin `--force`. Los comandos de verificación salen
de lo que indique el usuario o de lo que se detecte en el repositorio.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from factory.util import today

PLACEHOLDER = "TODO(factory)"

# (plantilla empaquetada, ruta en el destino, ejecutable)
FILES: tuple[tuple[str, str, bool], ...] = (
    ("AGENTS.md", "{entry}", False),
    ("CLAUDE.md", "CLAUDE.md", False),
    ("feature_list.json", "feature_list.json", False),
    ("progress.md", "progress.md", False),
    ("session-handoff.md", "session-handoff.md", False),
    ("init.sh", "init.sh", True),
    ("check.sh", "scripts/check.sh", True),
    ("factory.toml", "factory.toml", False),
    ("prompts/maker.md", "prompts/maker.md", False),
    ("prompts/checker.md", "prompts/checker.md", False),
    ("prompts/intake.md", "prompts/intake.md", False),
    ("goals/_template.md", "goals/_template.md", False),
    ("docs/harness/clean-state-checklist.md", "docs/harness/clean-state-checklist.md", False),
)


def read_template(name: str) -> str:
    return (resources.files("factory") / "templates" / name).read_text(encoding="utf-8")


@dataclass
class Detection:
    verify: list[str] = field(default_factory=list)
    install: str | None = None
    source: str = "ninguna"


def detect(target: Path) -> Detection:
    """Comandos de verificación e instalación según los manifiestos del repositorio."""
    makefile = target / "Makefile"
    if makefile.exists():
        text = makefile.read_text(encoding="utf-8", errors="replace")
        for name in ("check", "test"):
            if re.search(rf"^{name}\s*:", text, re.MULTILINE):
                setup = "make setup" if re.search(r"^setup\s*:", text, re.MULTILINE) else None
                return Detection([f"make {name}"], setup, "Makefile")
    package = target / "package.json"
    if package.exists():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {}) or {}
        except json.JSONDecodeError:
            scripts = {}
        verify = ["npm test"] if "test" in scripts else []
        verify += ["npm run lint"] if "lint" in scripts else []
        if verify:
            return Detection(verify, "npm install", "package.json")
    pyproject = target / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="replace")
        verify = ["python3 -m pytest -q"]
        if "ruff" in text:
            verify.append("python3 -m ruff check .")
        return Detection(verify, "python3 -m pip install -e .", "pyproject.toml")
    return Detection()


@dataclass
class InitResult:
    target: Path
    created: list[str] = field(default_factory=list)
    overwritten: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    detection: Detection = field(default_factory=Detection)

    def render(self) -> str:
        out = [f"Harness en {self.target}"]
        cmds = ", ".join(self.detection.verify) or "(ninguno)"
        out.append(f"Verificación ({self.detection.source}): {cmds}")
        for label, items in (
            ("Creados", self.created),
            ("Sobrescritos (--force)", self.overwritten),
            ("Omitidos (ya existían; usa --force para sobrescribir)", self.skipped),
        ):
            if items:
                out.append(f"{label}:")
                out.extend(f"  - {item}" for item in items)
        if self.placeholders:
            out.append("Marcadores pendientes de completar:")
            out.extend(f"  - {p}" for p in self.placeholders)
        out.append("Siguiente paso: completa los marcadores y ejecuta `factory doctor`.")
        return "\n".join(out)


def _check_steps(commands: list[str]) -> str:
    if not commands:
        return (
            f'echo "{PLACEHOLDER}: define los comandos de verificación en scripts/check.sh" >&2\n'
            "exit 1"
        )
    return "\n".join(f"run_step {shlex.quote(cmd)}" for cmd in commands)


def init_harness(
    target: Path,
    commands: list[str] | None = None,
    force: bool = False,
    entry_file: str = "AGENTS.md",
) -> InitResult:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"No existe el directorio destino: {target}")
    detection = detect(target)
    if commands:
        detection = Detection(commands, detection.install, "indicados por el usuario")
    install = detection.install or f'echo "{PLACEHOLDER}: define la instalación de dependencias"'
    values = {
        "{{PROJECT}}": target.name,
        "{{TODAY}}": today(),
        "{{START}}": "./init.sh",
        "{{VERIFY}}": "./scripts/check.sh",
        "{{VERIFY_LIST}}": "\n".join(f"  - `{c}`" for c in detection.verify)
        or f"  - {PLACEHOLDER}: define los comandos",
        "{{CHECK_STEPS}}": _check_steps(detection.verify),
        "{{INSTALL}}": install,
        "{{ENTRY}}": entry_file,
    }
    result = InitResult(target, detection=detection)
    for template, relative, executable in FILES:
        if template == "CLAUDE.md" and entry_file == "CLAUDE.md":
            continue  # el archivo de entrada ya es CLAUDE.md: no se añade la importación
        relative = relative.format(entry=entry_file)
        path = target / relative
        existed = path.exists()
        if existed and not force:
            result.skipped.append(relative)
            continue
        text = read_template(template)
        for key, value in values.items():
            text = text.replace(key, value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        (result.overwritten if existed else result.created).append(relative)
        if PLACEHOLDER in text:
            result.placeholders.append(f"{relative}: busca '{PLACEHOLDER}'")
    return result
