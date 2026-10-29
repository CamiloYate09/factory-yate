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


INTAKE_DECISIONS = ("ACCEPT", "NEEDS-INFO", "REJECT")
RISKS = ("low", "medium", "high")

INTAKE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["decision", "risk", "surfaces", "rescoped", "why"],
    "properties": {
        "decision": {"type": "string", "enum": list(INTAKE_DECISIONS)},
        "risk": {"type": "string", "enum": list(RISKS)},
        "surfaces": {"type": "array", "items": {"type": "string"}},
        "rescoped": {"type": "boolean"},
        "scope": {"type": "string"},
        "left_out": {"type": "array", "items": {"type": "string"}},
        "why": {"type": "string"},
        "question": {"type": "string"},
        "knowledge_queries": {"type": "array", "items": {"type": "string"}},
        "goal": {
            "type": "object",
            "required": ["objective", "acceptance"],
            "properties": {
                "objective": {"type": "string"},
                "acceptance": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "run"],
                        "properties": {"name": {"type": "string"}, "run": {"type": "string"}},
                    },
                },
                "scope": {
                    "type": "object",
                    "properties": {
                        "allow": {"type": "array", "items": {"type": "string"}},
                        "deny": {"type": "array", "items": {"type": "string"}},
                        "protected": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "body": {"type": "string"},
            },
        },
    },
}


@dataclass
class IntakeDecision:
    decision: str
    risk: str
    surfaces: list[str]
    rescoped: bool
    why: str
    scope: str = ""
    left_out: list[str] = field(default_factory=list)
    question: str = ""
    goal: dict[str, Any] = field(default_factory=dict)
    knowledge_queries: list[str] = field(default_factory=list)


def _str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def parse_intake(data: Any) -> tuple[IntakeDecision | None, list[str]]:
    """Valida la decisión del intake; con ACCEPT exige un objetivo con criterios ejecutables."""
    if not isinstance(data, dict):
        return None, ["la decisión del intake no es un objeto JSON"]
    errors = []
    if data.get("decision") not in INTAKE_DECISIONS:
        errors.append(f"decision debe ser uno de {INTAKE_DECISIONS}")
    if data.get("risk") not in RISKS:
        errors.append(f"risk debe ser uno de {RISKS}")
    if not _str_list(data.get("surfaces")):
        errors.append("surfaces debe ser una lista de texto")
    if not isinstance(data.get("rescoped"), bool):
        errors.append("rescoped debe ser booleano")
    if not _text(data.get("why")):
        errors.append("falta why")
    if "left_out" in data and not _str_list(data["left_out"]):
        errors.append("left_out debe ser una lista de texto")
    goal = data.get("goal") or {}
    if data.get("decision") == "ACCEPT":
        if not _text(data.get("scope")):
            errors.append("con ACCEPT hace falta scope")
        acceptance = goal.get("acceptance") if isinstance(goal, dict) else None
        if not isinstance(goal, dict) or not _text(goal.get("objective")):
            errors.append("con ACCEPT hace falta goal.objective")
        if (
            not isinstance(acceptance, list)
            or not acceptance
            or not all(
                isinstance(c, dict) and _text(c.get("name")) and _text(c.get("run"))
                for c in acceptance
            )
        ):
            errors.append("con ACCEPT hace falta goal.acceptance con al menos un {name, run}")
    queries = data.get("knowledge_queries", [])
    if not _str_list(queries):
        errors.append("knowledge_queries debe ser una lista de texto")
    elif data.get("decision") == "ACCEPT" and not [q for q in queries if q.strip()]:
        errors.append("con ACCEPT hace falta knowledge_queries (consultas en inglés)")
    if data.get("decision") == "NEEDS-INFO" and not _text(data.get("question")):
        errors.append("con NEEDS-INFO hace falta question")
    if errors:
        return None, errors
    return (
        IntakeDecision(
            decision=data["decision"],
            risk=data["risk"],
            surfaces=[s.strip() for s in data["surfaces"] if s.strip() and s.strip() != "none"],
            rescoped=data["rescoped"],
            why=data["why"].strip(),
            scope=str(data.get("scope", "")).strip(),
            left_out=list(data.get("left_out", [])),
            question=str(data.get("question", "")).strip(),
            goal=goal if isinstance(goal, dict) else {},
            knowledge_queries=[q.strip() for q in data.get("knowledge_queries", []) if q.strip()],
        ),
        [],
    )
