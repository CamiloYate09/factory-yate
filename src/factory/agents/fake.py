"""Agente simulado y guionizado para tests: sin red y sin coste real."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from factory.agents.base import AgentRequest, AgentResult


@dataclass
class FakeStep:
    """Lo que hace el agente en una invocación.

    `edits` mapea rutas relativas al cwd a contenido nuevo (`None` borra el archivo).
    Un checker con `edits` simula un rol de solo lectura que intenta escribir.
    """

    output: dict[str, Any] | None = None
    edits: dict[str, str | None] = field(default_factory=dict)
    cost_usd: float = 0.01
    input_tokens: int = 1000
    output_tokens: int = 200
    error: str | None = None
    timeout: bool = False
    permission_denials: list[Any] = field(default_factory=list)
    action: Callable[[AgentRequest], None] | None = None


def maker_done(summary: str = "hecho", **edits: str) -> FakeStep:
    """Informe `done` con ediciones; usa `**{"ruta/archivo.py": "contenido"}` para rutas."""
    return FakeStep(output={"status": "done", "summary": summary}, edits=dict(edits))


def verdict(result: str = "pass", *findings: dict[str, str]) -> FakeStep:
    return FakeStep(output={"verdict": result, "summary": "", "findings": list(findings)})


def finding(severity: str = "medium", location: str = "src/x.py:1", **extra: str) -> dict:
    return {
        "severity": severity,
        "location": location,
        "description": extra.get("description", "problema"),
        "evidence": extra.get("evidence", "evidencia"),
        "suggestion": extra.get("suggestion", "arreglarlo"),
    }


class FakeRunner:
    """Consume un guion por rol; si se agota, repite el último paso."""

    def __init__(
        self,
        maker: list[FakeStep] | None = None,
        checker: list[FakeStep] | None = None,
        intake: list[FakeStep] | None = None,
    ):
        self.scripts: dict[str, list[FakeStep]] = {
            "maker": list(maker or [maker_done()]),
            "checker": list(checker or [verdict("pass")]),
            "intake": list(intake or [FakeStep(output={})]),
        }
        self.calls: list[AgentRequest] = []

    def _next(self, role: str) -> FakeStep:
        script = self.scripts[role]
        return script.pop(0) if len(script) > 1 else script[0]

    def run(self, request: AgentRequest) -> AgentResult:
        self.calls.append(request)
        step = self._next(request.role)
        if step.action:
            step.action(request)
        for relative, content in step.edits.items():
            target = request.cwd / relative
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        if step.timeout:
            return AgentResult(ok=False, error="tiempo agotado", model=request.model)
        if step.error:
            return AgentResult(ok=False, error=step.error, model=request.model)
        return AgentResult(
            ok=True,
            text="",
            output=step.output,
            cost_usd=step.cost_usd,
            input_tokens=step.input_tokens,
            output_tokens=step.output_tokens,
            num_turns=1,
            model=request.model,
            permission_denials=list(step.permission_denials),
        )

    def calls_for(self, role: str) -> list[AgentRequest]:
        return [c for c in self.calls if c.role == role]
