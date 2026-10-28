"""Registros auditables: `results.tsv` (solo-añadir) y `events.jsonl` por ejecución."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from factory.agents.base import AgentRequest, AgentResult
from factory.util import CommandResult, now_iso

RESULTS_FILE = "results.tsv"
RESULTS_COLUMNS = (
    "timestamp",
    "run_id",
    "round",
    "commit",
    "score",
    "verdict",
    "decision",
    "cost_usd",
    "duration_s",
    "description",
)
EVENTS_FILE = "events.jsonl"
OUTPUT_LIMIT = 2000


def _clean(value: Any) -> str:
    return " ".join(str(value).split())


def append_result(state_dir: Path, **row: Any) -> None:
    """Añade una fila a `results.tsv`; nunca reescribe las filas existentes."""
    path = state_dir / RESULTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    row.setdefault("timestamp", now_iso())
    with path.open("a", encoding="utf-8", newline="") as handle:
        if new:
            handle.write("\t".join(RESULTS_COLUMNS) + "\n")
        handle.write("\t".join(_clean(row.get(col, "")) for col in RESULTS_COLUMNS) + "\n")


def read_results(state_dir: Path) -> list[dict[str, str]]:
    path = state_dir / RESULTS_FILE
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def truncate(text: str, limit: int = OUTPUT_LIMIT) -> str:
    """Conserva el final de la salida, que es donde suelen estar los errores."""
    return text if len(text) <= limit else "…" + text[-(limit - 1) :]


class EventLog:
    """Una línea JSON por invocación de agente o comando de verificación."""

    def __init__(self, run_dir: Path):
        self.path = run_dir / EVENTS_FILE

    def write(self, event_type: str, **fields: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": now_iso(), "type": event_type, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def agent(self, round_number: int, request: AgentRequest, result: AgentResult) -> None:
        self.write(
            "agent",
            round=round_number,
            role=request.role,
            model_requested=request.model,
            model=result.model or request.model,
            duration_s=round(result.duration_s, 3),
            ok=result.ok,
            error=result.error,
            cost_usd=result.cost_usd,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            num_turns=result.num_turns,
            permission_denials=result.permission_denials,
            output=result.output,
        )

    def command(self, round_number: int, name: str, result: CommandResult) -> None:
        self.write(
            "command",
            round=round_number,
            name=name,
            command=result.command,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            duration_s=round(result.duration_s, 3),
            output=truncate(result.output),
        )

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
