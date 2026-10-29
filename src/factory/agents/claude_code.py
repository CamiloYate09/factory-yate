"""Adaptador real: invoca `claude -p` en modo headless (diseño D2).

Reglas fijas: sesión nueva por invocación (`--no-session-persistence`, sin `--resume`),
presupuesto por llamada (`--max-budget-usd`) y nunca un modo que omita permisos.
El prompt va por stdin para no chocar con las opciones variádicas ni con límites de argv.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Any

from factory.agents.base import AgentRequest, AgentResult
from factory.config import FORBIDDEN_PERMISSION_MODES
from factory.util import command_env

FORBIDDEN_FLAGS = ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions")
FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
INSTALL_HINT = (
    "Instala Claude Code (>= 2.1) y comprueba `claude --version`, o ajusta [agent].command "
    "en factory.toml."
)


def build_argv(request: AgentRequest, command: str = "claude") -> list[str]:
    if request.permission_mode in FORBIDDEN_PERMISSION_MODES:
        raise ValueError(f"Modo de permisos prohibido: {request.permission_mode}")
    argv = [
        command,
        "-p",
        "--output-format",
        "json",
        "--no-session-persistence",
        "--model",
        request.model,
        "--permission-mode",
        request.permission_mode,
    ]
    if request.system_prompt:
        argv += ["--append-system-prompt", request.system_prompt]
    if request.allowed_tools:
        argv += ["--allowedTools", ",".join(request.allowed_tools)]
    if request.denied_tools:
        argv += ["--disallowedTools", ",".join(request.denied_tools)]
    if request.max_budget_usd is not None:
        argv += ["--max-budget-usd", f"{max(request.max_budget_usd, 0.01):.2f}"]
    if request.add_dirs:
        for path in request.add_dirs:  # una bandera por ruta: la opción es variádica
            argv += ["--add-dir", str(path)]
    if request.json_schema is not None:
        argv += ["--json-schema", json.dumps(request.json_schema, separators=(",", ":"))]
    assert not any(flag in argv for flag in FORBIDDEN_FLAGS)
    return argv


def _structured(data: dict[str, Any]) -> dict[str, Any] | None:
    """Salida validada por --json-schema: campo estructurado o, en su defecto, JSON en `result`."""
    for key in ("structured_output", "structuredOutput", "output"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    text = data.get("result")
    if not isinstance(text, str):
        return None
    candidates = [text.strip()]
    fenced = FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _model_used(data: dict[str, Any], requested: str) -> str:
    usage = data.get("modelUsage")
    if isinstance(usage, dict) and usage:
        return ",".join(sorted(usage))
    return requested


def parse_result(stdout: str, requested_model: str) -> AgentResult:
    """Convierte la salida `--output-format json` del CLI en un AgentResult."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        snippet = stdout.strip()[:300]
        return AgentResult(ok=False, error=f"salida ilegible del agente: {snippet!r}")
    if not isinstance(data, dict):
        return AgentResult(ok=False, error="salida ilegible del agente: no es un objeto JSON")
    usage = data.get("usage") or {}
    input_tokens = sum(
        int(usage.get(key) or 0)
        for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    )
    is_error = bool(data.get("is_error")) or data.get("subtype") not in (None, "success")
    text = data.get("result") if isinstance(data.get("result"), str) else ""
    return AgentResult(
        ok=not is_error,
        text=text,
        output=_structured(data),
        cost_usd=float(data.get("total_cost_usd") or 0.0),
        input_tokens=input_tokens,
        output_tokens=int(usage.get("output_tokens") or 0),
        num_turns=int(data.get("num_turns") or 0),
        duration_s=float(data.get("duration_ms") or 0) / 1000,
        model=_model_used(data, requested_model),
        session_id=data.get("session_id"),
        permission_denials=list(data.get("permission_denials") or []),
        error=(f"el agente terminó con error ({data.get('subtype')}): {text[:300]}")
        if is_error
        else None,
    )


class ClaudeCodeRunner:
    def __init__(self, command: str = "claude"):
        self.command = command

    def run(self, request: AgentRequest) -> AgentResult:
        argv = build_argv(request, self.command)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                input=request.prompt,
                cwd=request.cwd,
                env=command_env(request.cwd),
                capture_output=True,
                text=True,
                timeout=request.timeout_s,
            )
        except FileNotFoundError:
            return AgentResult(
                ok=False,
                model=request.model,
                error=f"No se encontró el ejecutable '{self.command}'. {INSTALL_HINT}",
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                ok=False,
                model=request.model,
                duration_s=time.monotonic() - started,
                error=f"tiempo agotado tras {request.timeout_s:.0f}s",
            )
        result = parse_result(proc.stdout, request.model)
        result.duration_s = result.duration_s or time.monotonic() - started
        if proc.returncode != 0 and result.ok:
            result.ok = False
            result.error = f"'{self.command}' terminó con código {proc.returncode}: " + (
                proc.stderr.strip()[:300] or result.text[:300]
            )
        elif not result.ok and proc.stderr.strip() and "ilegible" in (result.error or ""):
            result.error = f"{result.error}; stderr: {proc.stderr.strip()[:300]}"
        return result
