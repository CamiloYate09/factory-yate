"""Adaptador Strands: ejecuta cada rol con `strands-harness` dentro del proceso.

`strands` es un extra opcional (`pip install -e '.[strands]'`): se importa solo al invocar, de
modo que el resto de la fábrica, la verificación y los tests funcionan sin él (diseño D9).

Reglas fijas, equivalentes a las de `ClaudeCodeRunner`:
- un agente nuevo por invocación, sin sesión, memoria, skills, subagentes ni tareas en segundo
  plano (D2);
- solo las herramientas confinadas de `strands_tools`, traducidas con fallo cerrado (D3, D5, D6);
- coste en USD calculado por tokens; sin precio para el modelo no se invoca (D4);
- presupuesto por llamada como cota de tokens y tiempo límite con señal de cancelación (D7);
- salida estructurada extraída del texto y validada después por el orquestador (D8).
"""

from __future__ import annotations

import importlib
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from factory.agents.base import AgentRequest, AgentResult
from factory.agents.pricing import ModelPrice, cost_usd, missing_price_hint
from factory.agents.strands_tools import Toolset, UntranslatableTools, plan_tools
from factory.agents.structured import from_text, schema_instruction
from factory.config import FORBIDDEN_PERMISSION_MODES, StrandsConfig

INSTALL_HINT = (
    "El backend 'strands' necesita el extra opcional: `.venv/bin/pip install -e '.[strands]'` "
    '(o vuelve a `[agent] backend = "claude-code"` en factory.toml).'
)
OK_STOP_REASONS = ("end_turn", "stop_sequence")
CANCEL_GRACE_S = 5.0
MIN_BUDGET_USD = 0.01  # igual que `--max-budget-usd` en ClaudeCodeRunner
# Estimación del turno que se corta por tiempo: sus tokens llegan al final del stream (D7).
CHARS_PER_TOKEN = 3
IN_FLIGHT_OUTPUT_TOKENS = 4096


@dataclass
class AgentSpec:
    """Lo que la fábrica necesita para construir el agente de una invocación."""

    model_id: str
    instructions: str
    toolset: Toolset


AgentFactory = Callable[[AgentSpec], Callable[..., Any]]


@dataclass
class _Call:
    spec: AgentSpec
    prompt: str
    limits: dict[str, int]
    price: ModelPrice
    budget: float | None
    timeout_s: float | None
    cancel: threading.Event


def strands_available() -> bool:
    try:
        importlib.import_module("strands_harness")
    except ImportError:
        return False
    return True


def default_agent_factory(spec: AgentSpec) -> Callable[..., Any]:
    """Agente de `strands-harness` aislado; las opciones están fijadas por el diseño (D2)."""
    from strands import tool
    from strands.experimental.context_manager import ContextManager
    from strands_harness import create_harness

    tools = [tool(fn, name=name) for name, fn in spec.toolset.functions().items()]
    return create_harness(
        model=spec.model_id,
        instructions=spec.instructions or None,
        tools=tools,
        builtin_tools=[],
        builtin_plugins=[],
        mcp_servers=None,
        session=False,
        memory=False,
        skills=False,
        background_tasks=False,
        # Como "auto", pero sin `retrieve_context`: su patrón se evalúa con `re` dentro del proceso,
        # y un patrón costoso congelaría el tiempo límite (ver SEARCH_WORKER en strands_tools).
        context_manager=ContextManager(stash=False),
        callback_handler=None,  # sin esto, Strands imprime la respuesta en stdout
    )


def _usage(result: Any) -> dict[str, Any]:
    """Uso de toda la petición (incluidas llamadas auxiliares) o, si falta, el del agente."""
    context = getattr(result, "invocation_context", None)
    usage = getattr(context, "usage", None)
    if isinstance(usage, dict) and usage:
        return usage
    metrics = getattr(result, "metrics", None)
    return dict(getattr(metrics, "accumulated_usage", None) or {})


def _agent_usage(agent: Any) -> dict[str, Any]:
    """Uso acumulado por el agente hasta ahora: sirve cuando no hay resultado (error o tiempo)."""
    metrics = getattr(agent, "event_loop_metrics", None)
    return dict(getattr(metrics, "accumulated_usage", None) or {})


def _tokens(usage: dict[str, Any], key: str) -> int:
    return int(usage.get(key) or 0)


def _usage_cost(usage: dict[str, Any], price: ModelPrice) -> tuple[float, int, int]:
    """(coste, tokens de entrada con caché, tokens de salida) de un uso de Strands."""
    fresh = _tokens(usage, "inputTokens")
    cache_read = _tokens(usage, "cacheReadInputTokens")
    cache_write = _tokens(usage, "cacheWriteInputTokens")
    output = _tokens(usage, "outputTokens")
    cost = cost_usd(price, fresh, output, cache_read, cache_write)
    return cost, fresh + cache_read + cache_write, output


def _in_flight_cost(call: _Call, agent: Any) -> float:
    """Estimación del turno en curso: su contexto y una salida fija. Puede no ser exacta."""
    metrics = getattr(agent, "event_loop_metrics", None)
    context = getattr(metrics, "latest_context_size", None) or 0
    prompt = (len(call.prompt) + len(call.spec.instructions)) // CHARS_PER_TOKEN
    return cost_usd(call.price, max(context, prompt), IN_FLIGHT_OUTPUT_TOKENS)


class StrandsRunner:
    def __init__(self, config: StrandsConfig, agent_factory: AgentFactory | None = None):
        self.config = config
        self.agent_factory = agent_factory

    def run(self, request: AgentRequest) -> AgentResult:
        model_id = self.config.resolve_model(request.model)
        if request.permission_mode in FORBIDDEN_PERMISSION_MODES:
            return self._fail(model_id, f"Modo de permisos prohibido: {request.permission_mode}")
        price = self.config.prices.get(model_id)
        if price is None:
            return self._fail(model_id, missing_price_hint(model_id))
        cancel = threading.Event()
        try:
            toolset = plan_tools(
                request.allowed_tools,
                request.denied_tools,
                request.cwd,
                request.add_dirs,
                shell_timeout_s=request.timeout_s or 600,
                cancel=cancel,
            )
        except UntranslatableTools as exc:
            return self._fail(model_id, str(exc))
        factory = self.agent_factory
        if factory is None:
            if not strands_available():
                return self._fail(model_id, INSTALL_HINT)
            factory = default_agent_factory

        prompt = request.prompt
        if request.json_schema is not None:
            prompt += schema_instruction(request.json_schema)
        budget = None
        limits: dict[str, int] = {}
        if request.max_budget_usd is not None:
            budget = max(request.max_budget_usd, MIN_BUDGET_USD)
            if price.max_per_token > 0:
                tokens = math.floor(round(budget / price.max_per_token, 6))  # 1/2e-05 = 49999,99…
                limits["total_tokens"] = max(tokens, 1)
        spec = AgentSpec(model_id, request.system_prompt, toolset)
        call = _Call(spec, prompt, limits, price, budget, request.timeout_s, cancel)
        return self._invoke(factory, call)

    def _invoke(self, factory: AgentFactory, call: _Call) -> AgentResult:
        box: dict[str, Any] = {}

        def target() -> None:
            try:
                agent = factory(call.spec)
                box["agent"] = agent
                kwargs: dict[str, Any] = {"cancel_signal": call.cancel}
                if call.limits:
                    kwargs["limits"] = call.limits
                box["result"] = agent(call.prompt, **kwargs)
            except BaseException as exc:  # todo error vuelve como AgentResult
                box["error"] = exc

        started = time.monotonic()
        worker = threading.Thread(target=target, name="factory-strands-agent", daemon=True)
        worker.start()
        try:
            worker.join(call.timeout_s)
        except BaseException:
            # Ctrl-C: el comando del agente tiene su propia sesión y la señal no le llega, así que
            # hay que cancelarlo antes de que el motor restaure el worktree.
            call.cancel.set()
            worker.join(CANCEL_GRACE_S)
            raise
        timed_out = worker.is_alive()
        if timed_out:
            call.cancel.set()
            worker.join(CANCEL_GRACE_S)
        duration = time.monotonic() - started

        if timed_out:
            # La señal ya mató el comando de shell en curso; el hilo solo puede seguir esperando
            # al modelo, que Strands corta en el siguiente fragmento.
            error = f"tiempo agotado tras {call.timeout_s:.0f}s"
            return self._failed(call, box, duration, error, cut_short=True)
        if "error" in box:
            exc = box["error"]
            error = f"el backend strands falló ({type(exc).__name__}): {str(exc)[:300]}"
            return self._failed(call, box, duration, error)
        result = self._convert(box["result"], call.spec, call.price)
        result.duration_s = duration
        return result

    def _failed(
        self, call: _Call, box: dict[str, Any], duration: float, error: str, cut_short: bool = False
    ) -> AgentResult:
        """Error de agente con el coste de lo ya consumido.

        Una excepción cuesta solo lo registrado: con un error de credenciales es 0 y se aplica la
        regla de fallos consecutivos. Un tiempo agotado (`cut_short`) añade además la estimación
        del turno que se cortó, porque Strands no registra sus tokens.
        """
        if "result" in box:
            usage = _usage(box["result"])
        elif "agent" in box:
            usage = _agent_usage(box["agent"])
        else:
            usage = {}  # la fábrica falló antes de crear el agente: no hubo llamadas
        cost, input_tokens, output_tokens = _usage_cost(usage, call.price)
        finished = getattr(box.get("result"), "stop_reason", None) in OK_STOP_REASONS
        if cut_short and "agent" in box and not finished:  # cancelado devuelve un resultado
            estimate = _in_flight_cost(call, box["agent"])
            if call.budget is not None:
                estimate = min(estimate, max(call.budget - cost, 0.0))
            cost += estimate
        return AgentResult(
            ok=False,
            model=call.spec.model_id,
            duration_s=duration,
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=error,
        )

    def _convert(self, raw: Any, spec: AgentSpec, price: ModelPrice) -> AgentResult:
        usage = _usage(raw)
        cost, input_tokens, output = _usage_cost(usage, price)
        metrics = getattr(raw, "metrics", None)
        turns = int(usage.get("turns_taken") or getattr(metrics, "cycle_count", 0) or 0)
        text = str(raw).strip()
        stop = getattr(raw, "stop_reason", "end_turn")
        ok = stop in OK_STOP_REASONS
        error = None if ok else f"el agente terminó con error ({stop}): {text[:300]}"
        if ok and input_tokens + output == 0 and price.max_per_token > 0:
            # Sin uso no hay coste: aceptarlo desactivaría en silencio el presupuesto (D4).
            ok, error = False, "el backend strands no informó del uso de tokens; sin coste"
        return AgentResult(
            ok=ok,
            text=text,
            output=from_text(text),
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output,
            num_turns=turns,
            model=spec.model_id,
            error=error,
        )

    @staticmethod
    def _fail(model: str, error: str) -> AgentResult:
        return AgentResult(ok=False, model=model, error=error)
