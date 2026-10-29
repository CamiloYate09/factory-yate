"""Estado externo de cada ejecución (diseño D5).

`state.json` es la fuente de verdad; `loop-state.md` se genera a partir de él con el formato de
la plantilla del curso. Ambos se escriben de forma atómica tras cada ronda completa, así que
una interrupción deja siempre un estado legible que refleja la última ronda terminada.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from factory.util import atomic_write_text, now_iso

RUNNING = "running"
COMPLETED = "completed"
INTERRUPTED = "interrupted"
FINAL_STATUSES = (
    COMPLETED,
    "stalled",
    "max_rounds",
    "budget_exhausted",
    "blocked",
    "agent_error",
    INTERRUPTED,
)
MARK = {True: "✅ Pass", False: "❌ Fail"}


@dataclass
class RoundRecord:
    number: int
    started: str
    finished: str = ""
    maker_status: str = ""
    maker_summary: str = ""
    changed_files: list[str] = field(default_factory=list)
    criteria: dict[str, bool] = field(default_factory=dict)
    score: int = 0
    signature: str = ""
    checker_verdict: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    approved: bool = False
    decision: str = ""  # keep | revert | scope_revert | role_revert | error
    commit: str = ""
    cost_usd: float = 0.0
    maker_input_tokens: int = 0
    duration_s: float = 0.0
    human_needed: bool = False
    note: str = ""
    next_plan: str = ""
    protected_violations: list[str] = field(default_factory=list)
    reverted_to: str = ""  # commit al que volvió la rama si la ronda se revirtió
    maker_model: str = ""
    checker_model: str = ""

    @property
    def total(self) -> int:
        return len(self.criteria)


@dataclass
class RunState:
    run_id: str
    goal_id: str
    objective: str
    status: str = RUNNING
    started: str = field(default_factory=now_iso)
    finished: str = ""
    stop_reason: str = ""
    branch: str = ""
    base_commit: str = ""
    worktree: str = ""
    feature: str | None = None
    kind: str = "goal"  # goal | tick
    pid: int = field(default_factory=os.getpid)
    criteria_total: int = 0
    manual_checks: int = 0
    rounds: list[RoundRecord] = field(default_factory=list)
    best_score: int = -1
    best_round: int = 0
    best_commit: str = ""
    total_cost_usd: float = 0.0
    blockers: list[str] = field(default_factory=list)
    question: str = ""
    summary: str = ""
    parent_run_id: str = ""  # ejecución de la que parte un retrabajo
    start_commit: str = ""  # punta de la que parte la rama (= base salvo en retrabajo)
    landed_commit: str = ""  # commit de main tras `factory land`
    human_answer: str = ""  # retrabajo: respuesta humana recibida
    parent_question: str = ""  # retrabajo: pregunta que hizo la ejecución padre

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        rounds = [RoundRecord(**r) for r in data.get("rounds", [])]
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "rounds"}
        return cls(**known, rounds=rounds)


def new_run_id(goal_id: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{goal_id}-{secrets.token_hex(2)}"


def _elapsed(start: str, end: str) -> str:
    try:
        seconds = (
            datetime.fromisoformat(end or now_iso()) - datetime.fromisoformat(start)
        ).total_seconds()
    except ValueError:
        return "?"
    minutes = int(seconds // 60)
    return f"{minutes // 60}h {minutes % 60}m"


def render_loop_state(state: RunState, max_rounds: int | None = None) -> str:
    """`loop-state.md` con el formato de la plantilla del curso (lección 13)."""
    total = f" / {max_rounds}" if max_rounds else ""
    lines = [
        f"# Estado del loop: {state.goal_id}",
        "",
        "## Información básica",
        "",
        f"- **Ejecución**: `{state.run_id}`",
        f"- **Inicio**: {state.started}",
        f"- **Ronda actual**: {len(state.rounds)}{total}",
        f"- **Estado actual**: {state.status}",
        f"- **Tiempo total**: {_elapsed(state.started, state.finished)}",
        f"- **Rama**: `{state.branch}` (base `{state.base_commit[:10]}`)",
        f"- **Coste acumulado**: {state.total_cost_usd:.4f} USD",
        "",
        "## Objetivo",
        "",
        state.objective,
        "",
        "## Registro de rondas",
    ]
    for r in state.rounds:
        lines += [
            "",
            f"### Ronda {r.number}",
            "",
            f"- **Inicio**: {r.started}",
            f"- **Qué hizo el Maker** ({r.maker_status or '—'}): {r.maker_summary or '—'}",
            f"- **Resultado de verificación**: {MARK[r.approved]} "
            f"({r.score}/{r.total} criterios; checker: {r.checker_verdict or '—'})",
            "- **Problemas encontrados**:",
        ]
        failed = [name for name, ok in r.criteria.items() if not ok]
        issues = [f"criterio fallido: {name}" for name in failed]
        issues += [f"[{f['severity']}] {f['location']}: {f['description']}" for f in r.findings]
        if r.note:
            issues.append(r.note)
        lines += [f"  - {issue}" for issue in issues] or ["  - ninguno"]
        lines += [
            f"- **Decisión**: {r.decision}" + (f" (commit `{r.commit[:10]}`)" if r.commit else ""),
            f"- **Plan para la siguiente ronda**: {r.next_plan or '—'}",
            f"- **Requiere intervención humana**: {'Sí' if r.human_needed else 'No'}",
        ]
    passed = sum(1 for r in state.rounds if r.approved)
    findings = sum(len(r.findings) for r in state.rounds)
    files = {f for r in state.rounds for f in r.changed_files}
    lines += [
        "",
        "## Estadísticas acumuladas",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Rondas completadas | {len(state.rounds)} |",
        f"| Rondas aprobadas | {passed} |",
        f"| Rondas fallidas | {len(state.rounds) - passed} |",
        f"| Hallazgos del checker | {findings} |",
        f"| Intervenciones humanas | {sum(1 for r in state.rounds if r.human_needed)} |",
        f"| Archivos cambiados | {len(files)} |",
        f"| Mejor ronda | {state.best_round} ({max(state.best_score, 0)} criterios) |",
        "",
        "## Lista de bloqueos",
        "",
        *([f"- {b}" for b in state.blockers] or ["- ninguno"]),
        "",
        "## Resultado final",
        "",
    ]
    if state.is_final:
        lines += [
            f"- **Estado final**: {state.status}",
            f"- **Terminado**: {state.finished or '—'}",
            f"- **Motivo de parada**: {state.stop_reason or '—'}",
            f"- **Resumen**: {state.summary or '—'}",
        ]
        if state.question:
            lines.append(f"- **Pregunta para el humano**: {state.question}")
    else:
        lines.append("- En curso.")
    return "\n".join(lines) + "\n"


def build_summary(state: RunState, max_chars: int) -> str:
    """Resumen acotado para la siguiente ronda: bloqueos, mejor ronda y ronda más reciente primero.

    Nunca es proporcional al historial completo: el resto de rondas solo entra mientras quepa.
    """

    def describe(r: RoundRecord) -> str:
        failed = [n for n, ok in r.criteria.items() if not ok]
        parts = [
            f"Ronda {r.number}: {r.score}/{r.total} criterios, checker {r.checker_verdict or '—'}"
            f", decisión {r.decision}."
        ]
        if failed:
            parts.append(f"Fallaron: {', '.join(failed)}.")
        if r.note:
            parts.append(r.note)
        if r.maker_summary:
            parts.append(f"Maker: {r.maker_summary}")
        return " ".join(parts)

    sections = [f"Estado del loop '{state.goal_id}' tras {len(state.rounds)} ronda(s)."]
    if state.blockers:
        sections.append("Bloqueos activos: " + "; ".join(state.blockers))
    if state.rounds:
        last = state.rounds[-1]
        best = next((r for r in state.rounds if r.number == state.best_round), None)
        if best and best.number != last.number:
            sections.append("Mejor ronda (estado actual de la rama): " + describe(best))
        sections.append("Ronda más reciente: " + describe(last))
        older = [r for r in reversed(state.rounds[:-1]) if not best or r.number != best.number]
        for r in older:
            candidate = "Anterior: " + describe(r)
            if sum(len(s) + 1 for s in sections) + len(candidate) > max_chars:
                break
            sections.append(candidate)
    text = "\n".join(sections)
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


class RunStore:
    """Directorio `.factory/` del repo principal (fuera de los worktrees, ignorado por git)."""

    def __init__(self, state_dir: Path):
        self.base = state_dir

    @property
    def runs_dir(self) -> Path:
        return self.base / "runs"

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def create(self, state: RunState, goal_text: str) -> Path:
        directory = self.run_dir(state.run_id)
        directory.mkdir(parents=True, exist_ok=False)
        atomic_write_text(directory / "goal.md", goal_text)
        self.save(state)
        return directory

    def save(self, state: RunState, max_rounds: int | None = None) -> None:
        directory = self.run_dir(state.run_id)
        atomic_write_text(
            directory / "state.json",
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
        )
        atomic_write_text(directory / "loop-state.md", render_loop_state(state, max_rounds))

    def load(self, run_id: str) -> RunState:
        data = json.loads((self.run_dir(run_id) / "state.json").read_text(encoding="utf-8"))
        return RunState.from_dict(data)

    def list_runs(self) -> list[RunState]:
        if not self.runs_dir.exists():
            return []
        states = []
        for path in sorted(self.runs_dir.glob("*/state.json")):
            try:
                states.append(RunState.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, TypeError):
                continue
        return sorted(states, key=lambda s: s.started, reverse=True)
