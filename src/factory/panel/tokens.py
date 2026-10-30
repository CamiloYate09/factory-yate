"""Consumo de tokens: loops de factory (`events.jsonl`) y sesiones de Claude Code.

De las transcripciones solo se extraen modelo, `usage`, marca de tiempo e identificadores;
nunca el contenido de los mensajes. El USD solo existe donde se registró (los loops).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory.panel import (
    DESCRIPTION_MAX,
    day_of,
    is_number,
    number,
    read_jsonl,
    read_meta,
    unreadable,
)

LOOP_COUNTERS = ("input", "output", "turns", "cost_usd", "calls")
SESSION_COUNTERS = ("input", "cache_write", "cache_read", "output", "messages")
USAGE_FIELDS = {
    "input_tokens": "input",
    "cache_creation_input_tokens": "cache_write",
    "cache_read_input_tokens": "cache_read",
    "output_tokens": "output",
}
MAIN_AGENT = "principal"
UNKNOWN_AGENT = "subagente"
SYNTHETIC_MODEL = "<synthetic>"
WORKTREES_MARK = "--claude-worktrees-"
SESSIONS_LIMIT = 50


def _zero(counters: tuple[str, ...]) -> dict[str, int | float]:
    return dict.fromkeys(counters, 0)


def _add(acc: dict[str, int | float], row: dict[str, Any], counters: tuple[str, ...]) -> None:
    for name in counters:
        acc[name] += row.get(name, 0)


def _tokens(row: dict[str, Any]) -> int | float:
    return sum(row.get(name, 0) for name in ("input", "cache_write", "cache_read", "output"))


def _grouped(groups: dict[str, dict], label: str, by_label: bool = False) -> list[dict]:
    rows = [{label: key, **values} for key, values in groups.items()]
    if by_label:
        return sorted(rows, key=lambda r: r[label])
    return sorted(rows, key=lambda r: (-_tokens(r), r[label]))


def _rounded(row: dict[str, Any]) -> dict[str, Any]:
    if "cost_usd" in row:
        row["cost_usd"] = round(row["cost_usd"], 4)
    return row


# --- Loops de factory --------------------------------------------------------------------


def _loop_row(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "agent" or not isinstance(event.get("role"), str):
        return None
    fields = ("input_tokens", "output_tokens", "num_turns", "cost_usd")
    if not any(is_number(event.get(name)) for name in fields):
        return None
    return {
        "role": event["role"],
        "model": event.get("model") or event.get("model_requested") or "?",
        "day": day_of(event.get("ts")),
        "input": number(event.get("input_tokens")),
        "output": number(event.get("output_tokens")),
        "turns": number(event.get("num_turns")),
        "cost_usd": number(event.get("cost_usd")),
        "calls": 1,
    }


def loop_usage(state_dir: Path, warnings: list[str] | None = None) -> dict[str, Any]:
    """Consumo de los eventos `agent` de cada ejecución, por ejecución, rol, modelo y día."""
    runs: list[dict[str, Any]] = []
    by_role: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    total = _zero(LOOP_COUNTERS)
    for events in sorted((state_dir / "runs").glob("*/events.jsonl")):
        run = {"run_id": events.parent.name, "day": "", **_zero(LOOP_COUNTERS)}
        run_roles: dict[str, dict] = {}
        run_models: dict[str, dict] = {}
        for event in read_jsonl(events, warnings):
            row = _loop_row(event)
            if row is None:
                continue
            run["day"] = run["day"] or row["day"]
            for groups, key in (
                (run_roles, row["role"]),
                (run_models, row["model"]),
                (by_role, row["role"]),
                (by_model, row["model"]),
                (by_day, row["day"] or "?"),
            ):
                _add(groups.setdefault(key, _zero(LOOP_COUNTERS)), row, LOOP_COUNTERS)
            _add(run, row, LOOP_COUNTERS)
            _add(total, row, LOOP_COUNTERS)
        if run["calls"]:
            run["by_role"] = [_rounded(r) for r in _grouped(run_roles, "role")]
            run["by_model"] = [_rounded(r) for r in _grouped(run_models, "model")]
            runs.append(_rounded(run))
    runs.sort(key=lambda r: r["run_id"], reverse=True)
    return {
        "total": _rounded(total),
        "runs": runs,
        "by_role": [_rounded(r) for r in _grouped(by_role, "role")],
        "by_model": [_rounded(r) for r in _grouped(by_model, "model")],
        "by_day": [_rounded(r) for r in _grouped(by_day, "day", by_label=True)],
    }


# --- Sesiones de Claude Code -------------------------------------------------------------


def projects_dir(override: Path | None = None) -> Path:
    """Proyectos de Claude Code: `--projects-dir`, `$CLAUDE_CONFIG_DIR` o `~/.claude`."""
    if override is not None:
        return override
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "projects"


def slug(path: Path) -> str:
    """Nombre del directorio de proyecto que Claude Code usa para una ruta."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


@dataclass(frozen=True)
class Transcript:
    path: Path
    project: str  # "principal" o el nombre del worktree de `.claude/worktrees/`
    session: str  # sesión principal (la padre, en un subagente)
    agent_id: str = ""  # vacío en la transcripción de la sesión


def transcript_files(projects: Path, root: Path) -> list[Transcript]:
    """Transcripciones del repo y de sus worktrees `.claude/worktrees/*`, con subagentes.

    Los worktrees de los loops (`<repo>.factory-worktrees/…`) no comparten el prefijo y
    quedan fuera: su consumo ya cuenta en `events.jsonl`.
    """
    base = slug(root)
    try:
        candidates = sorted(d for d in projects.iterdir() if d.is_dir())
    except OSError:
        return []
    found: list[Transcript] = []
    for directory in candidates:
        if directory.name == base:
            project = MAIN_AGENT
        elif directory.name.startswith(base + WORKTREES_MARK):
            project = directory.name[len(base + WORKTREES_MARK) :]
        else:
            continue
        for path in sorted(directory.glob("*.jsonl")):
            found.append(Transcript(path, project, path.stem))
        for path in sorted(directory.glob("*/subagents/agent-*.jsonl")):
            found.append(
                Transcript(path, project, path.parent.parent.name, path.stem.removeprefix("agent-"))
            )
    return found


def _usage_row(data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if data.get("type") != "assistant":
        return None
    message = data.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
        return None
    model = message.get("model")
    if not isinstance(model, str) or not model or model == SYNTHETIC_MODEL:
        return None
    key = message.get("id") or data.get("requestId") or data.get("uuid")
    if not isinstance(key, str) or not key:
        return None
    usage = message["usage"]
    row: dict[str, Any] = {
        "model": model,
        "ts": data.get("timestamp") if isinstance(data.get("timestamp"), str) else "",
        "sidechain": data.get("isSidechain") is True,
    }
    for source, name in USAGE_FIELDS.items():
        row[name] = number(usage.get(source))
    return key, row


@dataclass
class _FileState:
    inode: int
    offset: int = 0
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)


class TranscriptReader:
    """Filas de `usage` por archivo. Recuerda lo leído: después solo lee lo añadido.

    Si un archivo encoge o cambia de inodo, se relee entero. Una línea final sin salto de
    línea (escritura a medias) se deja para la siguiente lectura.
    """

    def __init__(self) -> None:
        self._files: dict[Path, _FileState] = {}

    def rows(self, path: Path, warnings: list[str] | None = None) -> dict[str, dict[str, Any]]:
        try:
            stat = path.stat()
        except OSError as exc:
            self._files.pop(path, None)
            unreadable(path, exc, warnings)
            return {}
        state = self._files.get(path)
        if state is None or state.inode != stat.st_ino or stat.st_size < state.offset:
            state = self._files[path] = _FileState(stat.st_ino)
        if stat.st_size > state.offset:
            try:
                with path.open("rb") as handle:
                    handle.seek(state.offset)
                    chunk = handle.read(stat.st_size - state.offset)
            except OSError as exc:
                unreadable(path, exc, warnings)
                return state.rows
            end = chunk.rfind(b"\n")
            if end >= 0:
                for line in chunk[:end].split(b"\n"):
                    self._parse(line, state.rows)
                state.offset += end + 1
        return state.rows

    @staticmethod
    def _parse(line: bytes, rows: dict[str, dict[str, Any]]) -> None:
        if b'"usage"' not in line:  # descarte barato antes de decodificar el JSON
            return
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        parsed = _usage_row(data) if isinstance(data, dict) else None
        if parsed is not None:
            rows[parsed[0]] = parsed[1]  # la última fila de un mismo mensaje gana


def _meta(transcript: Transcript) -> tuple[str, str]:
    """Tipo y descripción declarados de un subagente (`agent-<id>.meta.json`)."""
    meta = read_meta(transcript.path)
    agent = meta.get("agentType") if isinstance(meta.get("agentType"), str) else ""
    description = meta.get("description") if isinstance(meta.get("description"), str) else ""
    return agent or UNKNOWN_AGENT, description[:DESCRIPTION_MAX]


def session_usage(
    projects: Path,
    root: Path,
    reader: TranscriptReader | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Consumo de las sesiones por día, modelo, tipo de agente y sesión (solo tokens)."""
    reader = reader or TranscriptReader()
    transcripts = transcript_files(projects, root)
    seen: set[str] = set()
    total = _zero(SESSION_COUNTERS)
    by_day: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}
    sessions: dict[str, dict[str, Any]] = {}
    for transcript in transcripts:
        agent, description = _meta(transcript) if transcript.agent_id else (MAIN_AGENT, "")
        for key, row in reader.rows(transcript.path, warnings).items():
            if key in seen:
                continue
            seen.add(key)
            row_agent = UNKNOWN_AGENT if not transcript.agent_id and row["sidechain"] else agent
            counted = {**row, "messages": 1}
            for groups, group_key in (
                (by_day, day_of(row["ts"]) or "?"),
                (by_model, row["model"]),
                (by_agent, row_agent),
            ):
                _add(
                    groups.setdefault(group_key, _zero(SESSION_COUNTERS)), counted, SESSION_COUNTERS
                )
            _add(total, counted, SESSION_COUNTERS)
            session = sessions.setdefault(
                transcript.session,
                {
                    "session": transcript.session,
                    "project": transcript.project,
                    "first": row["ts"],
                    "last": row["ts"],
                    "models": [],
                    **_zero(SESSION_COUNTERS),
                    "subagents": {},
                },
            )
            _add(session, counted, SESSION_COUNTERS)
            if row["ts"]:
                session["first"] = min(filter(None, (session["first"], row["ts"])))
                session["last"] = max(session["last"], row["ts"])
            if row["model"] not in session["models"]:
                session["models"].append(row["model"])
            if transcript.agent_id:
                sub = session["subagents"].setdefault(
                    transcript.agent_id,
                    {
                        "agent_id": transcript.agent_id,
                        "agent": agent,
                        "description": description,
                        **_zero(SESSION_COUNTERS),
                    },
                )
                _add(sub, counted, SESSION_COUNTERS)
    entering = total["input"] + total["cache_write"] + total["cache_read"]
    ordered = sorted(sessions.values(), key=lambda s: s["last"], reverse=True)[:SESSIONS_LIMIT]
    for session in ordered:
        session["subagents"] = sorted(session["subagents"].values(), key=lambda s: -_tokens(s))
    return {
        "projects_dir": str(projects),
        "transcripts": len(transcripts),
        "total": total,
        "cache_ratio": round(total["cache_read"] / entering, 4) if entering else 0,
        "by_day": _grouped(by_day, "day", by_label=True),
        "by_model": _grouped(by_model, "model"),
        "by_agent": _grouped(by_agent, "agent"),
        "sessions": ordered,
    }


def usage(
    state_dir: Path,
    projects: Path,
    root: Path,
    reader: TranscriptReader | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Sección `tokens` de la instantánea."""
    return {
        "loops": loop_usage(state_dir, warnings),
        "sessions": session_usage(projects, root, reader, warnings),
    }
