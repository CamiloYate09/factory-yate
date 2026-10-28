"""Lista de features: fuente de verdad del estado del trabajo (L08).

Las transiciones las controla el harness: solo `verify` puede promover a `passing`,
y solo si todos los comandos de verificación pasan; la evidencia queda registrada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory.util import CommandResult, atomic_write_text, git_head, now_iso, run_shell, today

VALID_STATUSES = ("not_started", "in_progress", "blocked", "passing")

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "priority": int,
    "title": str,
    "user_visible_behavior": str,
    "status": str,
    "verification": list,
    "evidence": list,
}


class FeatureError(Exception):
    pass


@dataclass(frozen=True)
class Issue:
    feature_id: str | None
    field: str
    message: str

    def __str__(self) -> str:
        prefix = f"[{self.feature_id}] " if self.feature_id else ""
        return f"{prefix}{self.field}: {self.message}"


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FeatureError(f"No existe la lista de features: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FeatureError(
            f"{path.name} no es JSON válido (línea {exc.lineno}): {exc.msg}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise FeatureError(f"{path.name} debe ser un objeto con una lista 'features'")
    return data


def save(path: Path, data: dict[str, Any]) -> None:
    data["last_updated"] = today()
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def missing_evidence(feature: dict[str, Any]) -> list[str]:
    """Comandos de verificación sin un registro de evidencia exitoso."""
    passed = {
        record.get("command")
        for record in feature.get("evidence") or []
        if isinstance(record, dict) and record.get("exit_code") == 0
    }
    return [cmd for cmd in feature.get("verification") or [] if cmd not in passed]


def validate_structure(data: dict[str, Any]) -> list[Issue]:
    """Campos obligatorios, estados válidos, comandos de verificación y evidencia de `passing`."""
    issues: list[Issue] = []
    seen: set[str] = set()
    for index, feature in enumerate(data.get("features", [])):
        if not isinstance(feature, dict):
            issues.append(Issue(None, f"features[{index}]", "debe ser un objeto"))
            continue
        fid = feature.get("id") if isinstance(feature.get("id"), str) else f"features[{index}]"
        for name, expected in REQUIRED_FIELDS.items():
            value = feature.get(name)
            if value is None:
                issues.append(Issue(fid, name, "campo obligatorio ausente"))
            elif not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
                issues.append(Issue(fid, name, f"debe ser de tipo {expected.__name__}"))
        if fid in seen:
            issues.append(Issue(fid, "id", "identificador duplicado"))
        seen.add(fid)
        status = feature.get("status")
        if isinstance(status, str) and status not in VALID_STATUSES:
            issues.append(
                Issue(
                    fid,
                    "status",
                    f"'{status}' no es válido; usa uno de {', '.join(VALID_STATUSES)}",
                )
            )
        verification = feature.get("verification")
        if isinstance(verification, list):
            if not verification:
                issues.append(Issue(fid, "verification", "necesita al menos un comando"))
            elif not all(isinstance(cmd, str) and cmd.strip() for cmd in verification):
                issues.append(
                    Issue(fid, "verification", "cada entrada debe ser un comando no vacío")
                )
        manual = feature.get("manual_checks")
        if manual is not None and not isinstance(manual, list):
            issues.append(Issue(fid, "manual_checks", "debe ser una lista de texto"))
        if status == "passing" and isinstance(verification, list) and verification:
            pending = missing_evidence(feature)
            if pending:
                issues.append(
                    Issue(
                        fid,
                        "evidence",
                        "está en 'passing' sin evidencia de: "
                        + ", ".join(pending)
                        + ". Usa `factory features verify` en lugar de editar el estado a mano.",
                    )
                )
    return issues


def validate_wip(data: dict[str, Any]) -> list[Issue]:
    active = [
        f.get("id", "?")
        for f in data.get("features", [])
        if isinstance(f, dict) and f.get("status") == "in_progress"
    ]
    if len(active) > 1:
        return [
            Issue(
                None,
                "status",
                f"WIP=1: hay {len(active)} features en 'in_progress': {', '.join(active)}",
            )
        ]
    return []


def validate(data: dict[str, Any]) -> list[Issue]:
    return validate_structure(data) + validate_wip(data)


def find(data: dict[str, Any], feature_id: str) -> dict[str, Any]:
    for feature in data.get("features", []):
        if isinstance(feature, dict) and feature.get("id") == feature_id:
            return feature
    ids = ", ".join(str(f.get("id")) for f in data.get("features", []) if isinstance(f, dict))
    raise FeatureError(f"No existe la feature '{feature_id}'. Disponibles: {ids or '(ninguna)'}")


def start(data: dict[str, Any], feature_id: str) -> None:
    """Marca la feature como activa respetando WIP=1."""
    feature = find(data, feature_id)
    if feature.get("status") == "passing":
        raise FeatureError(f"La feature '{feature_id}' ya está en 'passing'")
    others = [
        f.get("id")
        for f in data.get("features", [])
        if isinstance(f, dict) and f.get("status") == "in_progress" and f.get("id") != feature_id
    ]
    if others:
        raise FeatureError(
            f"WIP=1: '{others[0]}' ya está en 'in_progress'. Termínala o márcala 'blocked' primero."
        )
    feature["status"] = "in_progress"


@dataclass
class VerifyOutcome:
    feature_id: str
    results: list[CommandResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    @property
    def failed(self) -> CommandResult | None:
        return next((r for r in self.results if not r.ok), None)


def verify(
    data: dict[str, Any],
    feature_id: str,
    cwd: Path,
    run_id: str | None = None,
    timeout_s: float | None = None,
) -> VerifyOutcome:
    """Ejecuta la verificación y promueve a `passing` con evidencia solo si todo pasa."""
    feature = find(data, feature_id)
    commands = feature.get("verification") or []
    if not commands:
        raise FeatureError(f"La feature '{feature_id}' no tiene comandos de verificación")
    outcome = VerifyOutcome(feature_id)
    for command in commands:
        result = run_shell(command, cwd=cwd, timeout_s=timeout_s)
        outcome.results.append(result)
        if not result.ok:
            return outcome
    commit = git_head(cwd)
    date = now_iso()
    evidence = []
    for result in outcome.results:
        record: dict[str, Any] = {
            "command": result.command,
            "exit_code": result.exit_code,
            "date": date,
            "commit": commit,
        }
        if run_id:
            record["run_id"] = run_id
        evidence.append(record)
    feature["evidence"] = evidence
    feature["status"] = "passing"
    return outcome
