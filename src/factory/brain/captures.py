"""Capturas desde los loops (spec daily-brain): propuestas deterministas, pendientes de revisión.

Se generan solo a partir de los datos estructurados de la ejecución (hallazgos del checker,
pregunta y respuesta de un retrabajo, firma de estancamiento), sin invocar modelos. Una
salvaguarda de n-gramas sustituye cualquier fragmento copiado del conocimiento inyectado por
su cita: el texto de los libros nunca llega al cerebro diario.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from factory.brain import BrainError
from factory.brain.text import fold
from factory.state import COMPLETED, RunState
from factory.util import atomic_write_text, now_iso

NGRAM = 8
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


@dataclass
class Capture:
    id: str
    kind: str
    title: str
    text: str
    source: str
    tags: list[str] = field(default_factory=list)
    created: str = field(default_factory=now_iso)


@dataclass
class Injected:
    """Texto de referencia inyectado en la ejecución (para la salvaguarda)."""

    citation: str
    text: str


def _new_id(state: RunState, n: int) -> str:
    return f"{state.run_id}-c{n}-{secrets.token_hex(2)}"


def _fixed_findings(state: RunState) -> list[tuple[int, dict, int]]:
    approved = next((r for r in reversed(state.rounds) if r.approved), None)
    if state.status != COMPLETED or approved is None:
        return []
    final = {(f.get("location"), f.get("description")) for f in approved.findings}
    seen, found = set(), []
    for record in state.rounds:
        if record.number >= approved.number:
            continue
        for finding in record.findings:
            key = (finding.get("location"), finding.get("description"))
            if (
                finding.get("severity") in ("critical", "medium")
                and key not in final
                and key not in seen
            ):
                seen.add(key)
                found.append((record.number, finding, approved.number))
    return found


def propose(state: RunState, injected: list[Injected] | None = None) -> list[Capture]:
    """Capturas candidatas a partir de una ejecución terminada."""
    captures: list[Capture] = []
    source = f"run:{state.run_id}"
    for number, finding, approved in _fixed_findings(state):
        description = finding.get("description", "")
        captures.append(
            Capture(
                id=_new_id(state, len(captures) + 1),
                kind="gotcha",
                title=f"Hallazgo corregido: {description[:70]}",
                text=(
                    f"En la ejecución {state.run_id} (objetivo `{state.goal_id}`), el checker "
                    f"señaló en la ronda {number} un problema [{finding.get('severity')}] en "
                    f"{finding.get('location')}: {description}\n\n"
                    f"Evidencia: {finding.get('evidence', '')}\n\n"
                    f"Sugerencia: {finding.get('suggestion') or '—'}\n\n"
                    f"Se corrigió antes de la ronda aprobada ({approved})."
                ),
                source=source,
                tags=[state.goal_id, "checker", str(finding.get("severity"))],
            )
        )
    if state.parent_run_id and state.human_answer:
        question = state.parent_question or "(sin pregunta registrada)"
        captures.append(
            Capture(
                id=_new_id(state, len(captures) + 1),
                kind="decision",
                title=f"Decisión humana: {question[:70]}",
                text=(
                    f"Durante el objetivo `{state.goal_id}` la ejecución {state.parent_run_id} "
                    f"necesitó una decisión humana.\n\nPregunta: {question}\n\n"
                    f"Respuesta: {state.human_answer}"
                ),
                source=source,
                tags=[state.goal_id, "retrabajo"],
            )
        )
    if state.status == "stalled":
        last = state.rounds[-1] if state.rounds else None
        failed = [name for name, ok in (last.criteria.items() if last else []) if not ok]
        captures.append(
            Capture(
                id=_new_id(state, len(captures) + 1),
                kind="gotcha",
                title=f"Estancamiento en {state.goal_id}",
                text=(
                    f"La ejecución {state.run_id} se detuvo sin progreso: {state.stop_reason}.\n\n"
                    f"Criterios que seguían fallando: {', '.join(failed) or '—'}.\n\n"
                    f"Última nota del orquestador: {(last.note if last else '') or '—'}"
                ),
                source=source,
                tags=[state.goal_id, "estancamiento"],
            )
        )
    for capture in captures:
        capture.text = redact(capture.text, injected or [])
        capture.title = redact(capture.title, injected or [])
    return captures


def redact(text: str, injected: list[Injected]) -> str:
    """Sustituye cada fragmento de NGRAM palabras copiado de un texto inyectado por su cita."""
    if not injected:
        return text
    grams: dict[tuple[str, ...], str] = {}
    for item in injected:
        words = fold(item.text).split()
        for i in range(len(words) - NGRAM + 1):
            grams.setdefault(tuple(words[i : i + NGRAM]), item.citation)
    out_lines = []
    for line in text.split("\n"):
        words = line.split()
        folded = [fold(w) for w in words]
        covered: dict[int, str] = {}
        for i in range(len(words) - NGRAM + 1):
            citation = grams.get(tuple(folded[i : i + NGRAM]))
            if citation:
                for j in range(i, i + NGRAM):
                    covered[j] = citation
        if not covered:
            out_lines.append(line)
            continue
        rebuilt, i = [], 0
        while i < len(words):
            if i in covered:
                citation = covered[i]
                while i < len(words) and covered.get(i) == citation:
                    i += 1
                rebuilt.append(f"[texto de referencia omitido: ver {citation}]")
            else:
                rebuilt.append(words[i])
                i += 1
        out_lines.append(" ".join(rebuilt))
    return "\n".join(out_lines)


class CaptureStore:
    def __init__(self, state_dir: Path):
        self.pending_dir = state_dir / "brain" / "pending"
        self.rejected_dir = state_dir / "brain" / "rejected"

    def save(self, capture: Capture) -> Path:
        meta = {k: v for k, v in asdict(capture).items() if k != "text"}
        meta["pending"] = True
        front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
        path = self.pending_dir / f"{capture.id}.md"
        atomic_write_text(path, f"---\n{front}\n---\n\n{capture.text.rstrip()}\n")
        return path

    def load(self, path: Path) -> Capture:
        match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
        if not match:
            raise BrainError(f"Captura mal formada: {path}")
        meta = yaml.safe_load(match.group(1)) or {}
        meta.pop("pending", None)
        meta.pop("rejected_at", None)
        return Capture(**meta, text=match.group(2).strip())

    def pending(self) -> list[Capture]:
        if not self.pending_dir.exists():
            return []
        return [self.load(p) for p in sorted(self.pending_dir.glob("*.md"))]

    def path(self, capture_id: str) -> Path:
        path = self.pending_dir / f"{capture_id}.md"
        if not path.exists():
            raise BrainError(f"No hay ninguna captura pendiente '{capture_id}'")
        return path

    def remove(self, capture_id: str) -> None:
        self.path(capture_id).unlink()

    def reject(self, capture_id: str) -> Path:
        source = self.path(capture_id)
        self.rejected_dir.mkdir(parents=True, exist_ok=True)
        target = self.rejected_dir / source.name
        text = source.read_text(encoding="utf-8").replace(
            "pending: true", f"pending: false\nrejected_at: '{now_iso()}'", 1
        )
        atomic_write_text(target, text)
        source.unlink()
        return target
