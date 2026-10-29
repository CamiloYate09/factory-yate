"""Auditoría del harness en sus cinco subsistemas (L02, L03–L12).

No ejecuta la verificación (doctor forma parte de ella); solo comprueba que esté definida
y sea ejecutable.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from factory import features
from factory.brain.daily import map_ignored, repo_relative
from factory.brain.importer import leftovers, read_metadata
from factory.brain.libmap import problems as map_problems
from factory.config import Config
from factory.util import git

SUBSYSTEMS = ("instrucciones", "estado", "verificacion", "alcance", "ciclo_de_vida")
CRITICAL = "critical"
RECOMMENDED = "recommended"
WEIGHTS = {CRITICAL: 2, RECOMMENDED: 1}
MAX_ENTRY_LINES = 200
FALLBACK_ENTRY = "CLAUDE.md"
MAX_ACTIONS = 3

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
IMPORT_RE = re.compile(r"^@(\S+)", re.MULTILINE)


@dataclass
class Check:
    subsystem: str
    id: str
    description: str
    severity: str
    passed: bool
    fix: str = ""
    detail: str = ""


@dataclass
class Report:
    root: Path
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return not any(c.severity == CRITICAL and not c.passed for c in self.checks)

    def scores(self) -> dict[str, float]:
        result = {}
        for name in SUBSYSTEMS:
            checks = [c for c in self.checks if c.subsystem == name]
            total = sum(WEIGHTS[c.severity] for c in checks)
            earned = sum(WEIGHTS[c.severity] for c in checks if c.passed)
            result[name] = earned / total if total else 1.0
        return result

    def weakest(self) -> str | None:
        failing = {c.subsystem for c in self.checks if not c.passed}
        if not failing:
            return None
        scores = self.scores()
        return min((s for s in SUBSYSTEMS if s in failing), key=lambda s: scores[s])

    def actions(self) -> list[str]:
        weakest = self.weakest()
        failing = [c for c in self.checks if not c.passed]
        failing.sort(key=lambda c: (c.severity != CRITICAL, c.subsystem != weakest))
        return [c.fix for c in failing[:MAX_ACTIONS]]

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "ok": self.ok,
            "checks": [asdict(c) for c in self.checks],
            "subsystems": self.scores(),
            "weakest": self.weakest(),
            "actions": self.actions(),
        }


def _is_executable_command(command: str, root: Path) -> bool:
    try:
        first = shlex.split(command)[0]
    except (ValueError, IndexError):
        return False
    if "/" in first:
        path = (root / first).resolve()
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(first) is not None


def _longest_sections(lines: list[str], top: int = 3) -> str:
    sections: list[tuple[str, int]] = []
    current, count = "(inicio)", 0
    for line in lines:
        if line.startswith("## "):
            sections.append((current, count))
            current, count = line.strip(), 0
        count += 1
    sections.append((current, count))
    sections.sort(key=lambda item: item[1], reverse=True)
    return ", ".join(f"'{name}' ({n} líneas)" for name, n in sections[:top])


def _broken_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    targets = LINK_RE.findall(text) + IMPORT_RE.findall(text)
    broken = []
    for target in targets:
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        relative = target.split("#", 1)[0]
        if relative and not (path.parent / relative).exists():
            broken.append(target)
    return broken


def _instruction_checks(config: Config) -> list[Check]:
    root = config.root
    checks: list[Check] = []
    entry = root / config.harness.entry_file
    if not entry.exists() and (root / FALLBACK_ENTRY).exists():
        entry = root / FALLBACK_ENTRY
    exists = entry.exists()
    checks.append(
        Check(
            "instrucciones",
            "entry-exists",
            "Existe un archivo de instrucciones de entrada (AGENTS.md o CLAUDE.md)",
            CRITICAL,
            exists,
            "Crea AGENTS.md con resumen, comandos de arranque y verificación, restricciones "
            "duras y enlaces a documentos temáticos (o ejecuta `factory init`).",
        )
    )
    if not exists:
        return checks
    lines = entry.read_text(encoding="utf-8").splitlines()
    short = len(lines) <= MAX_ENTRY_LINES
    checks.append(
        Check(
            "instrucciones",
            "entry-length",
            f"{entry.name} tiene {MAX_ENTRY_LINES} líneas o menos",
            CRITICAL,
            short,
            f"Reduce {entry.name} a un router: mueve a docs/ temáticos las secciones más "
            f"largas: {_longest_sections(lines)}.",
            f"{len(lines)} líneas",
        )
    )
    broken = _broken_links(entry)
    checks.append(
        Check(
            "instrucciones",
            "entry-links",
            f"Los enlaces de {entry.name} resuelven",
            CRITICAL,
            not broken,
            f"Corrige o crea los destinos rotos en {entry.name}: {', '.join(broken)}.",
            ", ".join(broken),
        )
    )
    claude, agents = root / "CLAUDE.md", root / "AGENTS.md"
    canonical = not (claude.exists() and agents.exists()) or "@AGENTS.md" in claude.read_text(
        encoding="utf-8"
    )
    checks.append(
        Check(
            "instrucciones",
            "canonical-source",
            "CLAUDE.md importa la fuente canónica (@AGENTS.md) en lugar de duplicarla",
            RECOMMENDED,
            canonical,
            "Añade una línea `@AGENTS.md` a CLAUDE.md y elimina el contenido duplicado.",
        )
    )
    verify = config.effective_verify_command()
    mentions = bool(verify) and verify in "\n".join(lines)
    checks.append(
        Check(
            "instrucciones",
            "entry-mentions-verify",
            f"{entry.name} indica el comando de verificación",
            RECOMMENDED,
            mentions,
            f"Indica en {entry.name} el comando de verificación ({verify or 'por definir'}).",
        )
    )
    return checks


def _state_checks(config: Config) -> tuple[list[Check], dict | None]:
    path = config.path(config.harness.feature_list)
    data, problems = None, []
    try:
        data = features.load(path)
        problems = [str(i) for i in features.validate_structure(data)]
    except features.FeatureError as exc:
        problems = [str(exc)]
    checks = [
        Check(
            "estado",
            "feature-list-valid",
            f"{config.harness.feature_list} existe y es válida",
            CRITICAL,
            not problems,
            f"Corrige {config.harness.feature_list}: {'; '.join(problems[:3])}" if problems else "",
            "; ".join(problems),
        ),
        Check(
            "estado",
            "progress-exists",
            f"Existe el registro de progreso ({config.harness.progress_file})",
            CRITICAL,
            config.path(config.harness.progress_file).exists(),
            f"Crea {config.harness.progress_file} con el estado verificado actual y un registro "
            "por sesión.",
        ),
    ]
    return checks, data


def _verification_checks(config: Config) -> list[Check]:
    verify = config.effective_verify_command()
    checks = [
        Check(
            "verificacion",
            "verify-defined",
            "Hay un comando único de verificación",
            CRITICAL,
            verify is not None,
            "Define la ruta de verificación: crea scripts/check.sh (lint + formato + tests) o "
            "declara `verify_command` en [harness] de factory.toml.",
        )
    ]
    if verify:
        checks.append(
            Check(
                "verificacion",
                "verify-executable",
                f"El comando de verificación es ejecutable ({verify})",
                CRITICAL,
                _is_executable_command(verify, config.root),
                f"Haz ejecutable el comando de verificación: `chmod +x` o corrige la ruta "
                f"({verify}).",
            )
        )
    return checks


def _scope_checks(data: dict | None) -> list[Check]:
    wip = features.validate_wip(data) if data else []
    priorities = [
        f.get("priority") for f in (data or {}).get("features", []) if isinstance(f, dict)
    ]
    return [
        Check(
            "alcance",
            "wip-1",
            "Como máximo una feature en in_progress (WIP=1)",
            CRITICAL,
            data is not None and not wip,
            "Crea una lista de features legible para poder comprobar WIP=1."
            if data is None
            else "Deja una sola feature en in_progress; marca las demás como blocked o "
            "not_started." + (f" {wip[0].message}" if wip else ""),
        ),
        Check(
            "alcance",
            "unique-priorities",
            "Las prioridades de las features no se repiten",
            RECOMMENDED,
            len(priorities) == len(set(priorities)),
            "Asigna prioridades únicas para que la siguiente feature sea inequívoca.",
        ),
    ]


def _lifecycle_checks(config: Config) -> list[Check]:
    start = config.harness.start_command
    return [
        Check(
            "ciclo_de_vida",
            "start-command",
            f"Hay una ruta estándar de arranque ejecutable ({start})",
            CRITICAL,
            _is_executable_command(start, config.root),
            f"Crea {start} (prepara el entorno y ejecuta la verificación de referencia) y hazlo "
            "ejecutable.",
        ),
        Check(
            "ciclo_de_vida",
            "handoff",
            f"Existe la plantilla de handoff ({config.harness.handoff_file})",
            RECOMMENDED,
            config.path(config.harness.handoff_file).exists(),
            f"Crea {config.harness.handoff_file} para entregas compactas entre sesiones.",
        ),
        Check(
            "ciclo_de_vida",
            "clean-state-checklist",
            f"Existe la lista de cierre de sesión ({config.harness.checklist_file})",
            RECOMMENDED,
            config.path(config.harness.checklist_file).exists(),
            f"Crea {config.harness.checklist_file} con las dimensiones del clean state.",
        ),
    ]


def _brain_checks(config: Config) -> list[Check]:
    """Cerebro principal: nunca versionado (crítica); importado, válido y sin restos (si existe).

    Mapa de la biblioteca: solo campos de la lista blanca (crítica).
    """
    principal = config.principal_path
    checks = []
    try:
        relative = principal.relative_to(config.root.resolve())
    except ValueError:
        relative = None
    if relative is not None and (config.root / ".git").exists():
        tracked = git(config.root, "ls-files", "--", relative.as_posix(), check=False).splitlines()
        checks.append(
            Check(
                "estado",
                "brain-principal-untracked",
                f"El cerebro principal ({relative.as_posix()}/) no está versionado",
                CRITICAL,
                not tracked,
                f"Saca del índice los libros con `git rm -r --cached {relative.as_posix()}` y "
                f"asegúrate de que `/{relative.as_posix()}/` está en .gitignore.",
                ", ".join(tracked[:5]),
            )
        )
    if principal.is_dir():
        meta = read_metadata(principal)
        catalog = principal / "_catalog.jsonl"
        valid = (
            bool(meta)
            and catalog.is_file()
            and (hashlib.sha256(catalog.read_bytes()).hexdigest() == meta.get("catalog_sha256"))
        )
        checks.append(
            Check(
                "estado",
                "brain-principal-valid",
                "El cerebro principal tiene su registro de importación y su catálogo coincide",
                RECOMMENDED,
                valid,
                "Vuelve a importar el vault con `factory brain import <ruta-del-vault>`.",
            )
        )
        rest = leftovers(principal)
        checks.append(
            Check(
                "estado",
                "brain-principal-leftovers",
                "No quedan restos de importaciones interrumpidas",
                RECOMMENDED,
                not rest,
                "Borra los restos: " + ", ".join(p.name for p in rest),
            )
        )
    if config.map_path.is_dir():  # spec library-map: el mapa versionado nunca lleva texto
        ignored = map_ignored(config)
        checks.append(
            Check(
                "estado",
                "brain-map-versionable",
                "El mapa de la biblioteca no está en .gitignore (viaja con cada clon)",
                RECOMMENDED,
                not ignored,
                f"Quita `{ignored}` de .gitignore; el mapa no tiene texto de los libros.",
            )
        )
        found = map_problems(config.map_path)
        map_relative = repo_relative(config, config.map_path)
        checks.append(
            Check(
                "estado",
                "brain-map-sin-texto",
                "El mapa de la biblioteca solo contiene metadatos de la lista blanca (sin texto)",
                CRITICAL,
                not found,
                "Borra los archivos señalados o recupera el mapa con "
                f"`git restore {map_relative or config.map_path}/` "
                "(o regenéralo con `factory brain import <ruta-del-vault>`); no lo edites a mano. "
                "Si ya se commiteó texto, sácalo también del historial.",
                "; ".join(found[:5]),
            )
        )
    return checks


def audit(config: Config) -> Report:
    state_checks, data = _state_checks(config)
    checks = (
        _instruction_checks(config)
        + state_checks
        + _brain_checks(config)
        + _verification_checks(config)
        + _scope_checks(data)
        + _lifecycle_checks(config)
    )
    return Report(config.root, checks)


def render(report: Report) -> str:
    out = [f"Auditoría del harness: {report.root}"]
    scores = report.scores()
    for name in SUBSYSTEMS:
        out.append(f"\n{name} ({scores[name]:.0%})")
        for check in (c for c in report.checks if c.subsystem == name):
            label = "PASS" if check.passed else ("FAIL" if check.severity == CRITICAL else "WARN")
            out.append(f"  [{label}] [{check.severity.upper()}] {check.description}")
            if not check.passed:
                if check.detail:
                    out.append(f"         ✗ {check.detail}")
                out.append(f"         → {check.fix}")
    failed_critical = sum(1 for c in report.checks if c.severity == CRITICAL and not c.passed)
    failed_rec = sum(1 for c in report.checks if c.severity == RECOMMENDED and not c.passed)
    out.append(f"\nResultado: {failed_critical} crítica(s) y {failed_rec} recomendada(s) fallidas.")
    weakest = report.weakest()
    if weakest:
        out.append(
            f"Subsistema más débil (candidato a cuello de botella): {weakest} "
            f"({scores[weakest]:.0%})"
        )
        out.append("Acciones prioritarias:")
        out.extend(f"  {i}. {action}" for i, action in enumerate(report.actions(), 1))
    return "\n".join(out)
