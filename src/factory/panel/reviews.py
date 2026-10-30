"""Feed de revisiones: subagentes revisores (registro de hooks) y checker de los loops."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from factory.panel import read_jsonl
from factory.panel.hooks import EXCERPT_MAX, LOG, SEVERITIES
from factory.state import RunState

IN_PROGRESS = "en_curso"
# Inicio sin fin demasiado antiguo: la sesión se cerró con el revisor trabajando, o el
# lanzamiento falló (p. ej. un tipo de agente que la sesión aún no conocía) y no hubo subagente.
UNCLOSED = "sin_cierre"
UNCLOSED_AFTER_S = 2 * 3600
FEED_LIMIT = 200


def _parse(ts: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _seconds(start: str, end: datetime | None) -> float | None:
    begin = _parse(start)
    if begin is None or end is None:
        return None
    return round(max((end - begin).total_seconds(), 0.0), 1)


def _entry(source: str, reviewer: str, **values: Any) -> dict[str, Any]:
    entry = {
        "source": source,
        "status": IN_PROGRESS,
        "reviewer": reviewer,
        "description": "",
        "session_id": "",
        "tool_use_id": "",
        "run_id": "",
        "round": None,
        "model": "",
        "started": "",
        "finished": "",
        "duration_s": None,
        "verdict": "",
        "severities": dict.fromkeys(SEVERITIES, 0),
        "excerpt": "",
        "final": None,
    }
    entry.update(values)
    return entry


def _severities(value: Any) -> dict[str, int]:
    counts = dict.fromkeys(SEVERITIES, 0)
    if isinstance(value, dict):
        for name in SEVERITIES:
            if isinstance(value.get(name), int):
                counts[name] = value[name]
    return counts


def _close(entry: dict[str, Any], record: dict[str, Any]) -> None:
    verdict = record.get("verdict") or "sin_veredicto"
    entry.update(
        status=verdict,
        verdict=verdict,
        finished=record.get("ts", ""),
        duration_s=_seconds(entry["started"], _parse(record.get("ts", ""))),
        severities=_severities(record.get("severities")),
        excerpt=record.get("excerpt", "") if isinstance(record.get("excerpt"), str) else "",
        final=record.get("final") if isinstance(record.get("final"), bool) else None,
    )
    if record.get("description") and not entry["description"]:
        entry["description"] = record["description"]


Entries = list[dict[str, Any]]
ByTool = dict[str, dict[str, Any]]


def _on_start(record: dict[str, Any], entries: Entries, by_tool: ByTool) -> None:
    late = by_tool.get(record.get("tool_use_id") or "")
    if late is not None and not late["started"]:  # hooks asíncronos: llegó tras el fin
        late["started"] = record.get("ts", "")
        late["duration_s"] = _seconds(late["started"], _parse(late["finished"]))
        late["description"] = late["description"] or record.get("description", "")
        return
    entry = _entry(
        "hook",
        record.get("subagent_type", ""),
        description=record.get("description", ""),
        session_id=record.get("session_id", ""),
        tool_use_id=record.get("tool_use_id", ""),
        started=record.get("ts", ""),
    )
    entries.append(entry)
    if entry["tool_use_id"]:
        by_tool[entry["tool_use_id"]] = entry


def _last_open(entries: Entries, session: str, reviewer: str) -> dict[str, Any] | None:
    """Inicio más reciente sin cerrar de la misma sesión y del mismo tipo."""
    for entry in reversed(entries):
        if entry["status"] == IN_PROGRESS and (entry["session_id"], entry["reviewer"]) == (
            session,
            reviewer,
        ):
            return entry
    return None


def _on_stop(record: dict[str, Any], entries: Entries, by_tool: ByTool) -> None:
    session = record.get("session_id", "")
    reviewer = record.get("agent_type", "")
    tool_use_id = record.get("tool_use_id") or ""
    entry = by_tool.get(tool_use_id) if tool_use_id else None
    if entry is not None and entry["status"] != IN_PROGRESS:
        return  # fin repetido del mismo tool_use_id
    if entry is None and not tool_use_id:  # reserva solo si el fin no trae el id
        entry = _last_open(entries, session, reviewer)
    if entry is None:  # fin sin inicio: hook instalado a mitad, o inicio aún por llegar
        entry = _entry("hook", reviewer, session_id=session, tool_use_id=tool_use_id)
        entries.append(entry)
        if tool_use_id:
            by_tool[tool_use_id] = entry
    _close(entry, record)


def hook_reviews(
    state_dir: Path, now: datetime | None = None, warnings: list[str] | None = None
) -> list[dict[str, Any]]:
    """Revisiones de subagentes: une cada inicio (`PreToolUse`) con su fin (`SubagentStop`)."""
    now = now or datetime.now(UTC)
    entries: Entries = []
    by_tool: ByTool = {}
    for record in read_jsonl(state_dir / LOG, warnings):
        if record.get("review") is not True:
            continue
        if record.get("event") == "PreToolUse":
            _on_start(record, entries, by_tool)
        elif record.get("event") == "SubagentStop":
            _on_stop(record, entries, by_tool)
    for entry in entries:
        if entry["status"] == IN_PROGRESS:
            entry["duration_s"] = _seconds(entry["started"], now)
            if (entry["duration_s"] or 0) > UNCLOSED_AFTER_S:
                entry.update(status=UNCLOSED, duration_s=None)
    return entries


def _loop_excerpt(findings: list[dict[str, Any]]) -> str:
    lines = []
    for finding in findings:
        if isinstance(finding, dict):
            lines.append(
                f"[{finding.get('severity', '?')}] {finding.get('location', '')}: "
                f"{finding.get('description', '')}".strip()
            )
    return "\n".join(lines)[:EXCERPT_MAX]


def loop_reviews(runs: list[RunState]) -> list[dict[str, Any]]:
    """Veredicto del checker de cada ronda de los loops de factory."""
    entries = []
    for run in runs:
        for record in run.rounds:
            if not record.checker_verdict:
                continue
            counts = dict.fromkeys(SEVERITIES, 0)
            for finding in record.findings:
                severity = finding.get("severity") if isinstance(finding, dict) else None
                if severity in counts:
                    counts[severity] += 1
            entries.append(
                _entry(
                    "loop",
                    "checker",
                    status=record.checker_verdict,
                    verdict=record.checker_verdict,
                    description=run.goal_id,
                    run_id=run.run_id,
                    round=record.number,
                    model=record.checker_model,
                    started=record.started,
                    finished=record.finished,
                    severities=counts,
                    excerpt=_loop_excerpt(record.findings),
                )
            )
    return entries


def review_feed(
    state_dir: Path,
    runs: list[RunState],
    now: datetime | None = None,
    limit: int = FEED_LIMIT,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Feed de la más reciente a la más antigua (fin, o inicio si sigue en curso)."""
    entries = hook_reviews(state_dir, now, warnings) + loop_reviews(runs)

    def moment(entry: dict[str, Any]) -> float:
        stamp = _parse(entry["finished"] or entry["started"])
        return stamp.timestamp() if stamp else 0.0

    return sorted(entries, key=moment, reverse=True)[:limit]
