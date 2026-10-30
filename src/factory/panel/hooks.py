"""`factory hook`: registra los lanzamientos y fines de subagentes de Claude Code.

Lo llaman los hooks `PreToolUse` (herramienta `Agent`/`Task`) y `SubagentStop` de
`.claude/settings.json`. Cada evento añade una línea a `.factory/hooks/events.jsonl` del
repo principal, también desde un worktree.

Un hook nunca debe bloquear la sesión: siempre termina en 0, nunca escribe en stdout (Claude
Code lo interpretaría como control) y los errores van a stderr.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, TextIO

import yaml

from factory.panel import DESCRIPTION_MAX, main_root, read_jsonl, read_meta
from factory.panel import state_dir as configured_state_dir
from factory.util import find_root, now_iso

LOG = Path("hooks") / "events.jsonl"  # relativo al directorio de estado (`.factory/`)
AGENT_TOOLS = ("Agent", "Task")
DEFAULT_SUBAGENT = "general-purpose"
HANDBACK_TOOL = "SubagentHandback"  # herramienta con la que el subagente entrega su respuesta
REFEREE = "checker"
REVIEWER_KIND = "revisor"
VERDICTS = ("pass_with_minor", "pass", "fail")
NO_VERDICT = "sin_veredicto"
SEVERITIES = ("critical", "medium", "minor", "low")
EXCERPT_MAX = 4000
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")  # nombres que se usan en rutas

VERDICT_HEADING = re.compile(r"^\s*(#{1,6}\s*|\*\*)?veredicto\b\**\s*:?", re.IGNORECASE)
VERDICT_WORD = re.compile(r"\b(pass_with_minor|pass|fail)\b", re.IGNORECASE)
VERDICT_JSON = re.compile(r'"verdict"\s*:\s*"(pass_with_minor|pass|fail)"')
HEADING = re.compile(r"^\s*(#{1,6})\s")
FINDINGS_HEADING = re.compile(r"^\s*(#{1,6})\s*hallazgos\s*:?\s*$", re.IGNORECASE)
FINDING_LINE = re.compile(
    r"^\s*(?:#{2,6}|[-*]|\d+\.)\s.*?\[(critical|medium|minor|low)\]", re.IGNORECASE
)


def state_dir(cwd: Path) -> Path:
    """Directorio de estado (`.factory/` o `[loop] state_dir`) del repo principal."""
    return configured_state_dir(main_root(cwd))


def _text(value: Any, limit: int = DESCRIPTION_MAX) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def is_reviewer(agent_type: str, roots: list[Path]) -> bool:
    """El árbitro (`checker`) o un agente de `.claude/agents/` con `tipo: revisor`."""
    if agent_type == REFEREE:
        return True
    if not SAFE_NAME.match(agent_type):
        return False
    for root in roots:
        path = root / ".claude" / "agents" / f"{agent_type}.md"
        if path.is_file():
            return _frontmatter(path).get("tipo") == REVIEWER_KIND
    return False


def subagent_transcript(payload: dict[str, Any]) -> Path | None:
    """Transcripción del subagente: la del payload o la derivada de la de la sesión."""
    direct = payload.get("agent_transcript_path")
    if isinstance(direct, str) and direct:
        return Path(direct)
    transcript = payload.get("transcript_path")
    session = payload.get("session_id")
    agent_id = payload.get("agent_id")
    if not all(isinstance(v, str) and v for v in (transcript, session, agent_id)):
        return None
    if not (SAFE_NAME.match(session) and SAFE_NAME.match(agent_id)):
        return None
    return Path(transcript).parent / session / "subagents" / f"agent-{agent_id}.jsonl"


def _handback(blocks: list[Any]) -> str | None:
    """`message` de la última llamada a `SubagentHandback` de un mensaje, si la hay."""
    handback = None
    for block in blocks:
        if not (isinstance(block, dict) and block.get("name") == HANDBACK_TOOL):
            continue
        tool_input = block.get("input")
        handed = tool_input.get("message") if isinstance(tool_input, dict) else None
        if isinstance(handed, str) and handed.strip():
            handback = handed
    return handback


def _texts(blocks: list[Any]) -> list[str]:
    return [
        b["text"]
        for b in blocks
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
    ]


def last_response(transcript: Path | None) -> tuple[str, bool]:
    """Texto de la última respuesta del asistente que tiene texto, y si es la final.

    Una respuesta ocupa varias filas con el mismo `message.id` (una por bloque). Es final si
    después no hay más turnos (un subagente interrumpido acaba en un `tool_result`). Si el
    subagente entregó su respuesta con `SubagentHandback`, esa es la final.
    """
    if transcript is None:
        return "", False
    last_id: object = None
    parts: list[str] = []
    final = False
    handback: str | None = None
    for row in read_jsonl(transcript):
        message = row.get("message")
        if row.get("type") in ("user", "assistant"):
            final = False
        if row.get("type") != "assistant" or not isinstance(message, dict):
            continue
        content = message.get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        handback = _handback(blocks) or handback
        texts = _texts(blocks)
        if not texts:
            continue
        final = True
        message_id = message.get("id") or row.get("uuid")
        if message_id is not None and message_id == last_id:
            parts.extend(texts)
        else:
            last_id, parts = message_id, texts
    if handback is not None:
        return handback.strip(), True
    return "\n".join(parts).strip(), final


def verdict_of(text: str) -> str:
    """`pass`, `pass_with_minor` o `fail` tras una cabecera `Veredicto`; si no, `sin_veredicto`."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        heading = VERDICT_HEADING.match(line)
        if not heading:
            continue
        candidates = [line[heading.end() :]]
        for following in lines[index + 1 : index + 6]:
            if following.lstrip().startswith("#"):
                break
            candidates.append(following)
        for candidate in candidates:
            found = VERDICT_WORD.search(candidate)  # la primera de la línea, como se lee
            if found:
                return found.group(1).lower()
    found = VERDICT_JSON.search(text)
    return found.group(1) if found else NO_VERDICT


def findings_section(lines: list[str]) -> list[str]:
    """Líneas de la sección `Hallazgos` (hasta otra cabecera de su nivel), o todas si no hay.

    Así una segunda revisión que repasa en viñetas los hallazgos anteriores no los suma.
    """
    for index, line in enumerate(lines):
        heading = FINDINGS_HEADING.match(line)
        if not heading:
            continue
        section = []
        for following in lines[index + 1 :]:
            other = HEADING.match(following)
            if other and len(other.group(1)) <= len(heading.group(1)):
                break
            section.append(following)
        return section
    return lines


def severities_of(text: str) -> dict[str, int]:
    """Hallazgos por severidad: una por título o viñeta de hallazgo de la sección `Hallazgos`."""
    counts = dict.fromkeys(SEVERITIES, 0)
    for line in findings_section(text.splitlines()):
        found = FINDING_LINE.match(line)
        if found:
            counts[found.group(1).lower()] += 1
    return counts


def normalize(payload: dict[str, Any], roots: list[Path]) -> dict[str, Any] | None:
    """Línea del registro para un evento del hook, o `None` si el evento no interesa."""
    event = payload.get("hook_event_name")
    base = {
        "ts": now_iso(),
        "event": event,
        "session_id": _text(payload.get("session_id")),
        "cwd": _text(payload.get("cwd"), 1000),
        # Solo los nombres de los campos, para detectar cambios del formato de Claude Code.
        "payload_keys": sorted(k for k in payload if isinstance(k, str))[:50],
    }
    if event == "PreToolUse":
        if payload.get("tool_name") not in AGENT_TOOLS:
            return None
        tool_input = payload.get("tool_input")
        tool_input = tool_input if isinstance(tool_input, dict) else {}
        subagent = _text(tool_input.get("subagent_type")) or DEFAULT_SUBAGENT
        return {
            **base,
            "tool_use_id": _text(payload.get("tool_use_id")),
            "subagent_type": subagent,
            "description": _text(tool_input.get("description")),
            "background": tool_input.get("run_in_background") is True,
            "review": is_reviewer(subagent, roots),
        }
    if event == "SubagentStop":
        transcript = subagent_transcript(payload)
        meta = read_meta(transcript) if transcript is not None else {}
        agent_type = _text(payload.get("agent_type")) or _text(meta.get("agentType"))
        if not agent_type:  # agentes internos de Claude Code (p. ej. hooks de tipo prompt)
            return None
        review = is_reviewer(agent_type, roots)
        text, final = last_response(transcript) if review else ("", False)
        message = payload.get("last_assistant_message")
        if review and not final and isinstance(message, str) and message.strip():
            text, final = message.strip(), True  # la transcripción aún no tiene la respuesta
        return {
            **base,
            "agent_id": _text(payload.get("agent_id")),
            "agent_type": agent_type,
            "tool_use_id": _text(meta.get("toolUseId")),
            "description": _text(meta.get("description")),
            "review": review,
            "verdict": verdict_of(text) if review else "",
            "severities": severities_of(text) if review else {},
            "excerpt": text[:EXCERPT_MAX],
            "final": final,
        }
    return None


def append(log: Path, record: dict[str, Any]) -> None:
    """Añade una línea con bloqueo exclusivo: los subagentes terminan en paralelo."""
    log.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
    finally:
        os.close(fd)


def run(stdin: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Punto de entrada del hook. Siempre devuelve 0."""
    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    try:
        raw = stdin.read()
        try:
            payload = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict):
            print("factory hook: entrada vacía o no es un objeto JSON; se ignora", file=stderr)
            return 0
        cwd = payload.get("cwd")
        session_dir = Path(cwd) if isinstance(cwd, str) and Path(cwd).is_dir() else Path.cwd()
        roots = list(dict.fromkeys([find_root(session_dir), main_root(session_dir)]))
        record = normalize(payload, roots)
        if record is not None:
            append(state_dir(session_dir) / LOG, record)
    except BaseException as exc:  # un hook nunca debe romper la sesión
        try:
            print(f"factory hook: {type(exc).__name__}: {exc}", file=stderr)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
