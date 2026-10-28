"""Esquemas de salida de los roles y su validación local (sin depender de `jsonschema`).

El esquema se pasa a `claude -p --json-schema` y, además, el orquestador revalida la salida:
un veredicto que no cumple el esquema se trata como `fail` (spec maker-checker-loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("critical", "medium", "minor")
VERDICTS = ("pass", "fail", "pass_with_minor")
MAKER_STATUSES = ("done", "in_progress", "needs_human")

MAKER_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["status", "summary"],
    "properties": {
        "status": {"type": "string", "enum": list(MAKER_STATUSES)},
        "summary": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "self_check": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "question": {"type": "string"},
    },
}

FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["severity", "location", "description", "evidence", "suggestion"],
    "properties": {
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "location": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 1},
        "evidence": {"type": "string", "minLength": 1},
        "suggestion": {"type": "string"},
    },
}

CHECKER_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict", "findings"],
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": FINDING_SCHEMA},
    },
}


@dataclass
class Finding:
    severity: str
    location: str
    description: str
    evidence: str
    suggestion: str = ""

    def render(self) -> str:
        return (
            f"[{self.severity}] {self.location}: {self.description}\n"
            f"  evidencia: {self.evidence}\n  sugerencia: {self.suggestion or '-'}"
        )


@dataclass
class Verdict:
    verdict: str
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity in ("critical", "medium")]

    @property
    def approves(self) -> bool:
        """`pass`, o `pass_with_minor` sin hallazgos critical/medium."""
        return self.verdict in ("pass", "pass_with_minor") and not self.blocking


@dataclass
class MakerReport:
    status: str
    summary: str
    changed_files: list[str] = field(default_factory=list)
    self_check: str = ""
    risks: list[str] = field(default_factory=list)
    question: str = ""


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def parse_verdict(data: Any) -> tuple[Verdict | None, list[str]]:
    """Devuelve (veredicto, []) si es válido o (None, errores) si no cumple el esquema."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, ["el veredicto no es un objeto JSON"]
    if data.get("verdict") not in VERDICTS:
        errors.append(f"verdict debe ser uno de {VERDICTS}")
    raw_findings = data.get("findings")
    if not isinstance(raw_findings, list):
        errors.append("findings debe ser una lista")
        raw_findings = []
    findings = []
    for index, item in enumerate(raw_findings, 1):
        if not isinstance(item, dict):
            errors.append(f"findings[{index}] no es un objeto")
            continue
        if item.get("severity") not in SEVERITIES:
            errors.append(f"findings[{index}].severity debe ser uno de {SEVERITIES}")
        for key in ("location", "description", "evidence"):
            if not _text(item.get(key)):
                errors.append(f"findings[{index}] sin {key}")
        if "suggestion" in item and not isinstance(item["suggestion"], str):
            errors.append(f"findings[{index}].suggestion debe ser texto")
        findings.append(
            Finding(
                severity=str(item.get("severity")),
                location=str(item.get("location", "")),
                description=str(item.get("description", "")),
                evidence=str(item.get("evidence", "")),
                suggestion=str(item.get("suggestion", "")),
            )
        )
    if "summary" in data and not isinstance(data["summary"], str):
        errors.append("summary debe ser texto")
    if errors:
        return None, errors
    return Verdict(str(data["verdict"]), findings, str(data.get("summary", ""))), []


def parse_maker_report(data: Any) -> tuple[MakerReport | None, list[str]]:
    if not isinstance(data, dict):
        return None, ["el informe del maker no es un objeto JSON"]
    errors = []
    if data.get("status") not in MAKER_STATUSES:
        errors.append(f"status debe ser uno de {MAKER_STATUSES}")
    if not isinstance(data.get("summary"), str):
        errors.append("summary debe ser texto")
    for key in ("changed_files", "risks"):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            errors.append(f"{key} debe ser una lista de texto")
    if errors:
        return None, errors
    return (
        MakerReport(
            status=data["status"],
            summary=data["summary"],
            changed_files=list(data.get("changed_files", [])),
            self_check=str(data.get("self_check", "")),
            risks=list(data.get("risks", [])),
            question=str(data.get("question", "")),
        ),
        [],
    )
