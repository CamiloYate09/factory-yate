"""`factory status`: ejecuciones e indicadores de los cuatro costes silenciosos (L13).

- Deuda de verificación: ¿cuánto de lo "terminado" está comprobado por máquina?
- Deterioro de la comprensión: ¿cuánto código generado espera aún lectura humana?
- Rendición cognitiva: ¿cuántas revisiones se acumulan sin hacer?
- Explosión de tokens: ¿crece el contexto de entrada ronda a ronda?
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

from factory.config import Config
from factory.inbox import Inbox
from factory.state import RUNNING, RunState, RunStore

RECENT = 10


@dataclass
class Indicator:
    name: str
    value: str
    warning: bool = False
    detail: str = ""


@dataclass
class StatusReport:
    recent: list[RunState]
    active: list[RunState]
    orphans: list[RunState]
    indicators: list[Indicator]
    extra: list[str] = field(default_factory=list)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _age(created: str) -> str:
    try:
        delta = datetime.now(UTC) - datetime.fromisoformat(created)
    except ValueError:
        return "?"
    hours = int(delta.total_seconds() // 3600)
    return f"{hours // 24}d {hours % 24}h" if hours >= 24 else f"{hours}h"


def verification_debt(runs: list[RunState]) -> Indicator:
    machine = sum(r.criteria_total for r in runs)
    manual = sum(r.manual_checks for r in runs)
    total = machine + manual
    if not total:
        return Indicator("Deuda de verificación", "sin ejecuciones recientes")
    ratio = machine / total
    return Indicator(
        "Deuda de verificación",
        f"{ratio:.0%} de los criterios verificados por máquina",
        warning=manual > 0,
        detail=f"{manual} comprobación(es) solo humanas en features de ejecuciones recientes"
        if manual
        else "",
    )


def comprehension(inbox: Inbox, max_lines: int) -> Indicator:
    pending = inbox.pending()
    lines = sum(e.lines_changed for e in pending)
    files = len({f for e in pending for f in e.files_changed})
    return Indicator(
        "Deterioro de la comprensión",
        f"{lines} líneas en {files} archivo(s) pendientes de revisión humana",
        warning=lines > max_lines,
        detail=f"supera el umbral de {max_lines} líneas: revisa ramas antes de lanzar más loops"
        if lines > max_lines
        else "",
    )


def cognitive_surrender(inbox: Inbox, max_pending: int) -> Indicator:
    pending = inbox.pending()
    if not pending:
        return Indicator("Rendición cognitiva", "bandeja al día (0 pendientes)")
    oldest = pending[0]
    warning = len(pending) > max_pending
    return Indicator(
        "Rendición cognitiva",
        f"{len(pending)} entrada(s) pendiente(s); la más antigua: {oldest.id} "
        f"(hace {_age(oldest.created)})",
        warning=warning,
        detail=f"más de {max_pending} pendientes: el loop produce más rápido de lo que se revisa"
        if warning
        else "",
    )


def token_growth(runs: list[RunState], ratio: float) -> Indicator:
    flagged = []
    for run in runs:
        tokens = [r.maker_input_tokens for r in run.rounds if r.maker_input_tokens]
        if len(tokens) >= 2 and tokens[-1] > ratio * tokens[0]:
            flagged.append(f"{run.run_id} ({tokens[0]} → {tokens[-1]} tokens de entrada)")
    return Indicator(
        "Explosión de tokens",
        f"{len(flagged)} ejecución(es) con crecimiento > ×{ratio:g}"
        if flagged
        else "sin crecimiento anómalo del contexto",
        warning=bool(flagged),
        detail="; ".join(flagged),
    )


def collect(config: Config) -> StatusReport:
    runs = RunStore(config.state_path).list_runs()
    running = [r for r in runs if r.status == RUNNING]
    active = [r for r in running if _alive(r.pid)]
    orphans = [r for r in running if not _alive(r.pid)]
    recent = runs[:RECENT]
    inbox = Inbox(config.state_path)
    indicators = [
        verification_debt(recent),
        comprehension(inbox, config.alerts.pending_lines_max),
        cognitive_surrender(inbox, config.alerts.inbox_pending_max),
        token_growth(recent, config.alerts.token_growth_ratio),
    ]
    return StatusReport(recent, active, orphans, indicators)


def render(report: StatusReport) -> str:
    out = ["Ejecuciones recientes:"]
    if not report.recent:
        out.append("  (ninguna)")
    for run in report.recent:
        out.append(
            f"  {run.run_id}  {run.status:<16} rondas={len(run.rounds):<3} "
            f"coste={run.total_cost_usd:.4f} USD  rama={run.branch or '-'}"
        )
    out.append(f"\nActivas: {', '.join(r.run_id for r in report.active) or 'ninguna'}")
    if report.orphans:
        out.append(
            "Huérfanas (proceso terminado sin cerrar el estado): "
            + ", ".join(r.run_id for r in report.orphans)
        )
    out.append("\nCostes silenciosos:")
    for ind in report.indicators:
        out.append(f"  [{'AVISO' if ind.warning else 'OK'}] {ind.name}: {ind.value}")
        if ind.detail:
            out.append(f"         {ind.detail}")
    out.extend(report.extra)
    return "\n".join(out)
