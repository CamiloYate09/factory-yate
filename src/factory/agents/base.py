"""Interfaz común para invocar agentes (Claude Code real o simulado)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class AgentRequest:
    """Una invocación de un rol en una sesión nueva (nunca se reanuda una anterior)."""

    role: str
    prompt: str
    system_prompt: str
    cwd: Path
    model: str
    permission_mode: str
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    max_budget_usd: float | None = None
    timeout_s: float | None = None
    json_schema: dict[str, Any] | None = None


@dataclass
class AgentResult:
    ok: bool
    text: str = ""
    output: dict[str, Any] | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    num_turns: int = 0
    duration_s: float = 0.0
    model: str = ""
    session_id: str | None = None
    permission_denials: list[Any] = field(default_factory=list)
    error: str | None = None


class AgentRunner(Protocol):
    def run(self, request: AgentRequest) -> AgentResult: ...
