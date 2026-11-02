"""Escenarios de `agent-backends`: runner de Strands con agentes falsos (sin red ni `strands`)."""

import json
import signal
import subprocess
import sys
import threading
import time
import types
from dataclasses import dataclass, field

import pytest
from conftest import make_loop_repo, write_goal

from factory.agents.base import AgentRequest
from factory.agents.strands import AgentSpec, StrandsRunner
from factory.config import StrandsConfig, default_roles, load_config
from factory.engine import LoopEngine, exit_code
from factory.goal import load_goal
from factory.schemas import CHECKER_VERDICT_SCHEMA

VERDICT = {"verdict": "pass", "summary": "todo bien", "findings": []}
ZERO_USAGE = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
# Turno cortado con Opus 5.5: 4.096 tokens de salida a 20 USD/M, más el contexto a 4 USD/M.
IN_FLIGHT_OUTPUT_USD = 4096 * 20 / 1_000_000


@dataclass
class FakeMetrics:
    accumulated_usage: dict
    cycle_count: int = 1
    latest_context_size: int | None = None


@dataclass
class FakeContext:
    usage: dict


@dataclass
class FakeResult:
    """Lo que devuelve `strands.Agent.__call__` en lo que el runner usa."""

    text: str
    usage: dict = field(default_factory=lambda: {"inputTokens": 1000, "outputTokens": 100})
    stop_reason: str = "end_turn"
    with_context: bool = True

    @property
    def metrics(self):
        return FakeMetrics(dict(self.usage), cycle_count=2)

    @property
    def invocation_context(self):
        return FakeContext({**self.usage, "turns_taken": 3}) if self.with_context else None

    def __str__(self):
        return self.text


class FakeFactory:
    """Fábrica de agentes: registra cada agente creado y cómo se le llamó."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.specs: list[AgentSpec] = []
        self.calls: list[dict] = []

    def __call__(self, spec):
        self.specs.append(spec)

        def agent(prompt, **kwargs):
            self.calls.append({"prompt": prompt, **kwargs})
            return self.behaviour(spec, prompt, kwargs)

        agent.event_loop_metrics = FakeMetrics(dict(ZERO_USAGE))  # Strands arranca a ceros
        return agent


def _request(cwd, role="checker", **overrides):
    role_cfg = default_roles()[role]
    values = dict(
        role=role,
        prompt="revisa el diff",
        system_prompt="Eres el checker.",
        cwd=cwd,
        model=role_cfg.model,
        permission_mode=role_cfg.permission_mode,
        allowed_tools=role_cfg.allowed_tools,
        denied_tools=role_cfg.denied_tools,
        max_budget_usd=1.0,
        timeout_s=30,
        json_schema=CHECKER_VERDICT_SCHEMA,
    )
    values.update(overrides)
    return AgentRequest(**values)


def _verdict_text(*_):
    return FakeResult("Revisado.\n```json\n" + json.dumps(VERDICT) + "\n```")


# ------------------------------------------------------------------ aislamiento y opciones


def test_opciones_del_agente_por_defecto(tmp_path, monkeypatch):
    """La fábrica por defecto crea un agente aislado: sin sesión, memoria, skills ni subagentes."""
    captured = {}

    def create_harness(**kwargs):
        captured.update(kwargs)
        return lambda prompt, **_: FakeResult(json.dumps(VERDICT))

    harness = types.ModuleType("strands_harness")
    harness.create_harness = create_harness
    strands = types.ModuleType("strands")
    strands.tool = lambda fn, name: ("tool", name, fn)
    context = types.ModuleType("strands.experimental.context_manager")
    context.ContextManager = lambda **kwargs: ("context-manager", kwargs)
    monkeypatch.setitem(sys.modules, "strands_harness", harness)
    monkeypatch.setitem(sys.modules, "strands", strands)
    monkeypatch.setitem(sys.modules, "strands.experimental", types.ModuleType("x"))
    monkeypatch.setitem(sys.modules, "strands.experimental.context_manager", context)

    result = StrandsRunner(StrandsConfig()).run(_request(tmp_path))
    assert result.ok, result.error
    assert captured["model"] == "anthropic/claude-opus-5-5"
    assert captured["instructions"] == "Eres el checker."
    assert captured["builtin_tools"] == [] and captured["builtin_plugins"] == []
    assert captured["session"] is False and captured["memory"] is False
    assert captured["skills"] is False and captured["background_tasks"] is False
    assert captured["mcp_servers"] is None and captured["callback_handler"] is None
    # Sin almacén: `retrieve_context` evalúa patrones del modelo dentro del proceso.
    assert captured["context_manager"] == ("context-manager", {"stash": False})
    assert [name for _, name, _ in captured["tools"]] == ["read", "glob", "grep"]


def test_dos_rondas_consecutivas(tmp_path):
    factory = FakeFactory(_verdict_text)
    runner = StrandsRunner(StrandsConfig(), agent_factory=factory)
    runner.run(_request(tmp_path, prompt="ronda 1"))
    runner.run(_request(tmp_path, prompt="ronda 2"))
    assert len(factory.specs) == 2 and factory.specs[0] is not factory.specs[1]
    assert factory.specs[0].toolset is not factory.specs[1].toolset
    assert "ronda 1" not in factory.calls[1]["prompt"]


def test_modo_de_permisos_prohibido(tmp_path):
    factory = FakeFactory(_verdict_text)
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(
        _request(tmp_path, permission_mode="bypassPermissions")
    )
    assert not result.ok and "prohibido" in result.error
    assert factory.specs == []


def test_herramienta_sin_traduccion_no_llama_al_modelo(tmp_path):
    factory = FakeFactory(_verdict_text)
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(
        _request(tmp_path, allowed_tools=["Read", "NotebookEdit"], denied_tools=[])
    )
    assert not result.ok and "NotebookEdit" in result.error
    assert result.cost_usd == 0 and factory.specs == []


# ------------------------------------------------------------------ coste y presupuesto


def test_modelo_sin_precio(tmp_path):
    factory = FakeFactory(_verdict_text)
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(
        _request(tmp_path, model="anthropic/claude-desconocido")
    )
    assert not result.ok and result.cost_usd == 0
    assert 'agent.strands.prices."anthropic/claude-desconocido"' in result.error
    assert factory.specs == []


def test_coste_con_cache_y_tokens(tmp_path):
    usage = {
        "inputTokens": 100_000,
        "outputTokens": 10_000,
        "cacheReadInputTokens": 1_000_000,
        "cacheWriteInputTokens": 20_000,
    }
    factory = FakeFactory(lambda *_: FakeResult(json.dumps(VERDICT), usage=usage))
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(_request(tmp_path))
    # Opus 5.5: 0,1M×4 + 0,01M×20 + 1M×0,2 + 0,02M×5 = 0,4 + 0,2 + 0,2 + 0,1
    assert result.cost_usd == pytest.approx(0.9)
    assert result.input_tokens == 1_120_000 and result.output_tokens == 10_000
    assert result.num_turns == 3
    assert result.model == "anthropic/claude-opus-5-5"


def test_uso_del_agente_si_no_hay_contexto(tmp_path):
    factory = FakeFactory(lambda *_: FakeResult(json.dumps(VERDICT), with_context=False))
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(_request(tmp_path))
    assert result.input_tokens == 1000 and result.num_turns == 2


def test_cota_de_tokens_por_presupuesto(tmp_path):
    factory = FakeFactory(_verdict_text)
    runner = StrandsRunner(StrandsConfig(), agent_factory=factory)
    runner.run(_request(tmp_path, max_budget_usd=1.0))
    # Precio más alto de Opus 5.5: 20 USD/M → 1 USD da para 50.000 tokens como mucho.
    assert factory.calls[0]["limits"] == {"total_tokens": 50_000}
    runner.run(_request(tmp_path, max_budget_usd=0.0))
    assert factory.calls[1]["limits"] == {"total_tokens": 500}  # mínimo de 0,01 USD
    runner.run(_request(tmp_path, max_budget_usd=None))
    assert "limits" not in factory.calls[2]


def test_limite_alcanzado_es_un_error_con_coste(tmp_path):
    factory = FakeFactory(lambda *_: FakeResult("a medias", stop_reason="limit_total_tokens"))
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(_request(tmp_path))
    assert not result.ok and "limit_total_tokens" in result.error
    assert result.cost_usd > 0


# ------------------------------------------------------------------ resultado y errores


def test_veredicto_del_checker(tmp_path):
    factory = FakeFactory(_verdict_text)
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(_request(tmp_path))
    assert result.ok and result.output == VERDICT
    assert '"verdict"' in factory.calls[0]["prompt"]  # el esquema va en el prompt


def test_json_precedido_de_prosa(tmp_path):
    factory = FakeFactory(lambda *_: FakeResult("He revisado todo. " + json.dumps(VERDICT)))
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(_request(tmp_path))
    assert result.output == VERDICT


def test_excepcion_del_proveedor(tmp_path):
    def falla(*_):
        raise RuntimeError("AuthenticationError: invalid x-api-key")

    result = StrandsRunner(StrandsConfig(), agent_factory=FakeFactory(falla)).run(
        _request(tmp_path)
    )
    assert not result.ok
    assert "invalid x-api-key" in result.error and "RuntimeError" in result.error
    assert result.cost_usd == 0  # no hubo tokens: se aplica la regla de fallos consecutivos


def test_tiempo_agotado_en_el_primer_turno_estima_el_coste(tmp_path):
    cancelado = threading.Event()

    def bloqueado(_spec, _prompt, kwargs):
        kwargs["cancel_signal"].wait(10)
        cancelado.set()
        raise RuntimeError("cancelado")

    result = StrandsRunner(StrandsConfig(), agent_factory=FakeFactory(bloqueado)).run(
        _request(tmp_path, timeout_s=0.2, max_budget_usd=0.5)
    )
    assert not result.ok and "tiempo agotado" in result.error
    assert cancelado.wait(2)  # la señal de cancelación llegó al agente
    # Uso a ceros, como Strands a mitad del stream: no cuesta 0 ni agota el presupuesto.
    assert IN_FLIGHT_OUTPUT_USD < result.cost_usd < 0.5


def test_estimacion_del_turno_cortado_topada_por_el_presupuesto(tmp_path):
    def bloqueado(_spec, _prompt, kwargs):
        kwargs["cancel_signal"].wait(10)
        raise RuntimeError("cancelado")

    result = StrandsRunner(StrandsConfig(), agent_factory=FakeFactory(bloqueado)).run(
        _request(tmp_path, timeout_s=0.2, max_budget_usd=0.05)
    )
    assert result.cost_usd == pytest.approx(0.05)


# ------------------------------------------------------------------ con el motor de rondas


def _loop_factory(cost_tokens=1000):
    """Maker que escribe a.txt con su herramienta `write` y checker que aprueba."""

    def behaviour(spec, _prompt, _kwargs):
        usage = {"inputTokens": cost_tokens, "outputTokens": 100}
        if "write" in spec.toolset.names:
            spec.toolset.write("a.txt", "1\n")
            report = {"status": "done", "summary": "creé a.txt"}
            return FakeResult(json.dumps(report), usage=usage)
        return FakeResult(json.dumps(VERDICT), usage=usage)

    return FakeFactory(behaviour)


def _run(root, factory, **goal_kwargs):
    config = load_config(root)
    goal = load_goal(write_goal(root, **goal_kwargs), config.loop)
    runner = StrandsRunner(config.agent.strands, agent_factory=factory)
    return config, LoopEngine(config, goal, runner, echo=lambda _: None).run()


def test_loop_completo_con_strands(tmp_path):
    root = make_loop_repo(tmp_path)
    factory = _loop_factory()
    config, state = _run(root, factory)
    assert state.status == "completed" and exit_code(state) == 0
    assert state.total_cost_usd > 0
    eventos = [
        json.loads(line)
        for path in config.state_path.rglob("events.jsonl")
        for line in path.read_text().splitlines()
    ]
    agentes = [e for e in eventos if e["type"] == "agent"]
    assert {e["role"] for e in agentes} == {"maker", "checker"}
    assert all(e["cost_usd"] > 0 for e in agentes)
    assert not (root / "a.txt").exists()  # el maker escribió en su worktree, no en el repo


def test_presupuesto_agotado(tmp_path):
    root = make_loop_repo(tmp_path)

    def gasta(spec, _prompt, _kwargs):
        # Sonnet 5.5: 300.000 tokens de entrada = 0,6 USD por invocación del maker.
        return FakeResult(
            json.dumps({"status": "done", "summary": "nada"}),
            usage={"inputTokens": 300_000, "outputTokens": 0},
        )

    _, state = _run(root, FakeFactory(gasta), budget=1.0, max_rounds=8, no_progress=8)
    assert state.status == "budget_exhausted" and exit_code(state) == 5
    assert state.total_cost_usd >= 1.0


# ------------------------------------------------------------------ hallazgos del checker


class MeteredAgent:
    """Agente que registra uso en `event_loop_metrics`, como `strands.Agent`, y luego falla."""

    def __init__(self, usage, fail=None, block=False, context=None):
        self.event_loop_metrics = FakeMetrics(dict(usage), latest_context_size=context)
        self.fail = fail
        self.block = block

    def __call__(self, prompt, **kwargs):
        if self.block:
            kwargs["cancel_signal"].wait(10)
        raise self.fail or RuntimeError("fallo")


def test_excepcion_tras_consumir_tokens_cuesta(tmp_path):
    agent = MeteredAgent(
        {"inputTokens": 200_000, "outputTokens": 10_000},
        fail=RuntimeError("MaxTokensReachedException"),
    )
    result = StrandsRunner(StrandsConfig(), agent_factory=lambda _spec: agent).run(
        _request(tmp_path)
    )
    assert not result.ok and "MaxTokensReachedException" in result.error
    assert result.cost_usd == pytest.approx(1.0)  # Opus 5.5: 0,2M×4 + 0,01M×20
    assert result.input_tokens == 200_000 and result.output_tokens == 10_000


def test_fabrica_que_falla_antes_de_crear_el_agente_no_cuesta(tmp_path):
    def sin_credenciales(_spec):
        raise RuntimeError("NoCredentialsError")

    result = StrandsRunner(StrandsConfig(), agent_factory=sin_credenciales).run(_request(tmp_path))
    assert not result.ok and "NoCredentialsError" in result.error and result.cost_usd == 0


def test_tiempo_agotado_carga_lo_consumido_y_el_turno_cortado(tmp_path):
    agent = MeteredAgent(
        {"inputTokens": 10_000, "outputTokens": 0, "totalTokens": 10_000},
        block=True,
        context=50_000,
    )
    result = StrandsRunner(StrandsConfig(), agent_factory=lambda _spec: agent).run(
        _request(tmp_path, timeout_s=0.2, max_budget_usd=1.0)
    )
    assert not result.ok and "tiempo agotado" in result.error
    # 0,04 consumidos + 0,2 del contexto del turno cortado + la salida estimada; lejos de la cota,
    # así que sigue la regla de errores consecutivos y no agota el presupuesto.
    assert result.cost_usd == pytest.approx(0.04 + 0.2 + IN_FLIGHT_OUTPUT_USD)
    assert result.input_tokens == 10_000  # los tokens reportados son solo los registrados


def test_ctrl_c_mata_el_comando_en_curso(tmp_path):
    comando = "python -c \"__import__('time').sleep(1.5) or open('termino.txt', 'w')\""

    def ejecuta(spec, _prompt, _kwargs):
        return spec.toolset.shell(comando)

    def interrumpe(_signum, _frame):
        raise KeyboardInterrupt

    request = _request(
        tmp_path,
        role="maker",
        allowed_tools=["Read", "Bash(python -c:*)"],
        denied_tools=[],
        timeout_s=60,
    )
    previo = signal.signal(signal.SIGALRM, interrumpe)
    signal.setitimer(signal.ITIMER_REAL, 0.3)
    try:
        with pytest.raises(KeyboardInterrupt):
            StrandsRunner(StrandsConfig(), agent_factory=FakeFactory(ejecuta)).run(request)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previo)
    time.sleep(2)
    assert not (tmp_path / "termino.txt").exists()


def test_resultado_sin_uso_falla_cerrado(tmp_path):
    factory = FakeFactory(lambda *_: FakeResult(json.dumps(VERDICT), usage={}))
    result = StrandsRunner(StrandsConfig(), agent_factory=factory).run(_request(tmp_path))
    assert not result.ok and "uso de tokens" in result.error


def test_tiempo_agotado_mata_el_comando_en_curso(tmp_path):
    """La cancelación mata el comando de shell: no sigue ejecutándose tras el reset del worktree."""
    comando = "python -c \"__import__('time').sleep(1.5) or open('termino.txt', 'w')\""

    def ejecuta(spec, _prompt, _kwargs):
        return spec.toolset.shell(comando)

    request = _request(
        tmp_path,
        role="maker",
        allowed_tools=["Read", "Bash(python -c:*)"],
        denied_tools=[],
        timeout_s=0.3,
    )
    started = time.monotonic()
    result = StrandsRunner(StrandsConfig(), agent_factory=FakeFactory(ejecuta)).run(request)
    assert not result.ok and "tiempo agotado" in result.error
    assert time.monotonic() - started < 1.5  # no esperó a que el comando terminara
    time.sleep(2)
    assert not (tmp_path / "termino.txt").exists()  # el proceso murió con la cancelación


def test_patron_costoso_no_congela_el_tiempo_limite(tmp_path):
    """En un subproceso con tiempo límite externo: una regresión no debe colgar la suite."""
    script = """
import sys
from pathlib import Path
from factory.agents.base import AgentRequest
from factory.agents.strands import StrandsRunner
from factory.config import StrandsConfig

work = Path(sys.argv[1])
(work / "f.txt").write_text("a" * 40 + "!\\n")
factory = lambda spec: lambda prompt, **_: spec.toolset.grep("(a+)+$")
request = AgentRequest(
    role="checker", prompt="x", system_prompt="", cwd=work, model="opus",
    permission_mode="dontAsk", allowed_tools=["Grep"], timeout_s=0.5,
)
print(StrandsRunner(StrandsConfig(), agent_factory=factory).run(request).error)
"""
    salida = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert "tiempo agotado" in salida.stdout
