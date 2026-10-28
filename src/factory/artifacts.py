"""Artefactos legibles por ronda (spec loop-state).

Los genera el orquestador a partir de datos estructurados, no los agentes: así el formato no
depende de que un modelo lo respete. Cada archivo empieza con líneas `CLAVE: valor` hasta la
primera línea en blanco; `read_header` las lee.
"""

from __future__ import annotations

from pathlib import Path

from factory.records import truncate
from factory.schemas import Verdict
from factory.state import RoundRecord, RunState
from factory.verify import Verification

OUTPUT_TAIL = 2000


def header(**fields: object) -> str:
    lines = [f"{key.upper()}: {value}" for key, value in fields.items() if value not in (None, "")]
    return "\n".join(lines) + "\n\n"


def read_header(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            break
        key, _, value = line.partition(":")
        fields[key.strip().upper()] = value.strip()
    return fields


def render_maker(record: RoundRecord) -> str:
    lines = [
        header(
            status=record.maker_status or "sin informe",
            model=record.maker_model,
            cost_usd=f"{record.cost_usd:.4f}",
        ),
        f"# Ronda {record.number}: maker",
        "",
        "## Resumen",
        "",
        record.maker_summary or "(sin resumen)",
        "",
        "## Archivos cambiados",
        "",
        *([f"- {path}" for path in record.changed_files] or ["- (ninguno)"]),
    ]
    if record.note:
        lines += ["", "## Notas del orquestador", "", record.note]
    return "\n".join(lines) + "\n"


def _gate(record: RoundRecord, verification: Verification | None) -> str:
    if record.decision in ("scope_revert", "protected_revert"):
        return "FAIL"
    if verification is None:
        return "NOT_RUN"
    return "PASS" if verification.passed else "FAIL"


def render_checks(record: RoundRecord, verification: Verification | None) -> str:
    score = f"{verification.score}/{verification.total}" if verification else ""
    lines = [
        header(
            gate=_gate(record, verification),
            commit=record.commit,
            score=score,
            reverted_to=record.reverted_to,
            decision=record.decision,
        ),
        f"# Ronda {record.number}: verificación",
        "",
        "## Rutas protegidas",
        "",
        *([f"- {v}" for v in record.protected_violations] or ["Sin cambios en rutas protegidas."]),
        "",
        "## Criterios",
        "",
    ]
    if verification is None:
        lines.append(f"No se ejecutaron ({record.decision or 'sin decisión'}).")
    else:
        for name, result in verification.results.items():
            mark = "✅" if result.ok else "❌"
            suffix = " (tiempo agotado)" if result.timed_out else ""
            lines.append(f"- {mark} {name}: `{result.command}` → código {result.exit_code}{suffix}")
            if not result.ok:
                lines += ["", "```", truncate(result.output.strip(), OUTPUT_TAIL), "```", ""]
    if record.reverted_to and record.decision == "revert":
        lines += ["", f"Ratchet: la rama volvió a `{record.reverted_to}` (mejor ronda registrada)."]
    return "\n".join(lines).rstrip() + "\n"


def render_review(record: RoundRecord, verdict: Verdict | None) -> str:
    value = record.checker_verdict or "no_invocado"
    lines = [
        header(verdict=value, model=record.checker_model),
        f"# Ronda {record.number}: checker",
        "",
    ]
    if verdict is None:
        lines.append(f"Sin veredicto válido ({value}). {record.note}".strip())
    elif not verdict.findings:
        lines.append(verdict.summary or "Sin hallazgos.")
    else:
        if verdict.summary:
            lines += [verdict.summary, ""]
        lines += ["## Hallazgos", ""]
        for i, finding in enumerate(verdict.findings, 1):
            lines += [
                f"### {i}. [{finding.severity}] {finding.location}",
                f"- Descripción: {finding.description}",
                f"- Evidencia: {finding.evidence}",
                f"- Sugerencia: {finding.suggestion or '—'}",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def render_decision(state: RunState) -> str:
    lines = [
        header(
            result=state.status,
            reason=state.stop_reason,
            branch=state.branch,
            best_round=state.best_round,
            base=state.base_commit,
            parent=getattr(state, "parent_run_id", ""),
            landed=getattr(state, "landed_commit", ""),
        ),
        f"# Decisión: {state.goal_id}",
        "",
        state.summary or "",
    ]
    if state.question:
        lines += ["", "## Pregunta para el humano", "", state.question]
    if state.blockers:
        lines += ["", "## Bloqueos y avisos", "", *[f"- {b}" for b in state.blockers]]
    return "\n".join(lines).rstrip() + "\n"


def render_land_checks(
    gate: str,
    commit: str,
    main: str,
    branch_tip: str,
    verification: Verification | None,
    protected: list[str],
    conflicts: list[str],
) -> str:
    """Informe de `factory land` en land/checks.md (spec run-landing)."""
    lines = [
        header(gate=gate, commit=commit, main=main, branch=branch_tip),
        "# Integración: verificación del merge exacto",
        "",
        "## Conflictos",
        "",
        *([f"- {path}" for path in conflicts] or ["Ninguno."]),
        "",
        "## Rutas protegidas (lado de la rama)",
        "",
        *([f"- {v}" for v in protected] or ["Sin cambios en rutas protegidas."]),
        "",
        "## Criterios sobre el merge",
        "",
    ]
    if verification is None:
        lines.append("No se ejecutaron.")
    else:
        for name, result in verification.results.items():
            mark = "✅" if result.ok else "❌"
            lines.append(f"- {mark} {name}: `{result.command}` → código {result.exit_code}")
            if not result.ok:
                lines += ["", "```", truncate(result.output.strip(), OUTPUT_TAIL), "```", ""]
    return "\n".join(lines).rstrip() + "\n"
