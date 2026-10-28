"""Bandeja de revisión humana: una entrada por ejecución terminada o escalado.

Es el punto donde el humano recupera el juicio que el loop no puede tomar (L13): nada se integra
en `main` sin pasar por aquí.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from factory.state import RunState
from factory.util import atomic_write_text, now_iso

PENDING = "pending"
REVIEWED = "reviewed"
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


class InboxError(LookupError):
    pass


@dataclass
class InboxEntry:
    id: str
    goal_id: str
    kind: str = "run"  # run | escalation
    origin: str = "goal"  # goal (factory goal run) | tick (factory tick)
    status: str = PENDING
    created: str = field(default_factory=now_iso)
    reviewed_at: str | None = None
    result: str = ""
    stop_reason: str = ""
    branch: str = ""
    files_changed: list[str] = field(default_factory=list)
    lines_changed: int = 0
    cost_usd: float = 0.0
    question: str = ""
    body: str = ""

    def meta(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("body")
        return data


class Inbox:
    def __init__(self, state_dir: Path):
        self.dir = state_dir / "inbox"

    def path(self, entry_id: str) -> Path:
        return self.dir / f"{entry_id}.md"

    def save(self, entry: InboxEntry) -> Path:
        front = yaml.safe_dump(entry.meta(), allow_unicode=True, sort_keys=False).strip()
        path = self.path(entry.id)
        atomic_write_text(path, f"---\n{front}\n---\n{entry.body.rstrip()}\n")
        return path

    def load(self, path: Path) -> InboxEntry:
        match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
        if not match:
            raise InboxError(f"Entrada de bandeja mal formada: {path}")
        meta = yaml.safe_load(match.group(1)) or {}
        return InboxEntry(**meta, body=match.group(2))

    def entries(self, status: str | None = None) -> list[InboxEntry]:
        if not self.dir.exists():
            return []
        items = [self.load(p) for p in sorted(self.dir.glob("*.md"))]
        items = [e for e in items if status is None or e.status == status]
        return sorted(items, key=lambda e: e.created)

    def pending(self) -> list[InboxEntry]:
        return self.entries(PENDING)

    def pending_for(
        self, goal_id: str, kind: str = "run", origin: str | None = None
    ) -> list[InboxEntry]:
        return [
            e
            for e in self.pending()
            if e.goal_id == goal_id and e.kind == kind and origin in (None, e.origin)
        ]

    def ack(self, entry_id: str) -> InboxEntry:
        path = self.path(entry_id)
        if not path.exists():
            raise InboxError(f"No hay ninguna entrada '{entry_id}' en la bandeja")
        entry = self.load(path)
        entry.status = REVIEWED
        entry.reviewed_at = now_iso()
        self.save(entry)
        return entry


def run_entry(
    state: RunState,
    files_changed: list[str],
    lines_changed: int,
    diffstat: str = "",
) -> InboxEntry:
    """Entrada de bandeja para una ejecución terminada, con todo lo necesario para revisarla."""
    open_findings = state.rounds[-1].findings if state.rounds else []
    whats = [f"- Ronda {r.number}: {r.maker_summary}" for r in state.rounds if r.maker_summary]
    lines = [
        f"# {state.goal_id}: {state.status}",
        "",
        f"**Objetivo**: {state.objective}",
        f"**Motivo de parada**: {state.stop_reason}",
        f"**Rama a revisar**: `{state.branch}` (base `{state.base_commit[:10]}`)",
        f"**Rondas**: {len(state.rounds)} · **Coste**: {state.total_cost_usd:.4f} USD",
        "",
        "## Archivos cambiados",
        "",
        "```",
        diffstat.strip() or "\n".join(files_changed) or "(ninguno)",
        "```",
        "",
        "## Qué se hizo y por qué",
        "",
        *(whats or ["- (sin informes del maker)"]),
        "",
        "## Hallazgos sin resolver",
        "",
        *(
            [
                f"- [{f.get('severity')}] {f.get('location')}: {f.get('description')}"
                for f in open_findings
            ]
            or ["- ninguno"]
        ),
        "",
        "## Bloqueos y avisos",
        "",
        *([f"- {b}" for b in state.blockers] or ["- ninguno"]),
        "",
        "## Preguntas abiertas",
        "",
        f"- {state.question}" if state.question else "- ninguna",
        "",
        "## Cómo revisar",
        "",
        f"- `git log --oneline {state.base_commit[:10]}..{state.branch}`",
        f"- `git diff {state.base_commit[:10]}...{state.branch}`",
        f"- Estado completo: `.factory/runs/{state.run_id}/loop-state.md`",
        f"- Al terminar: `factory inbox ack {state.run_id}`",
    ]
    return InboxEntry(
        id=state.run_id,
        goal_id=state.goal_id,
        kind="run",
        origin=state.kind,
        result=state.status,
        stop_reason=state.stop_reason,
        branch=state.branch,
        files_changed=files_changed,
        lines_changed=lines_changed,
        cost_usd=round(state.total_cost_usd, 6),
        question=state.question,
        body="\n".join(lines),
    )
