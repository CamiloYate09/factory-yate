"""`StrandsRunner` con el `strands.Agent` real y un modelo falso: sin red y sin coste.

Cubre lo que los agentes falsos no pueden: el envoltorio de `strands.tool`, el uso real, la
cancelación a mitad del stream y que nada se escriba en disco. Se omite sin el extra `strands`.
"""

import asyncio
import json

import pytest

from factory.agents.strands import IN_FLIGHT_OUTPUT_TOKENS, StrandsRunner
from factory.config import StrandsConfig, default_roles
from factory.schemas import CHECKER_VERDICT_SCHEMA

strands_harness = pytest.importorskip("strands_harness")

from strands.models import Model  # noqa: E402

from factory.agents.base import AgentRequest  # noqa: E402

VERDICT = {"verdict": "pass", "summary": "todo bien", "findings": []}
USAGE = {"inputTokens": 1000, "outputTokens": 100, "totalTokens": 1100}


class ScriptedModel(Model):
    """Primer turno: pide la herramienta `read`. Segundo: responde con el veredicto."""

    def __init__(self, block=False):
        self.turn = 0
        self.block = block

    def update_config(self, **_):
        pass

    def get_config(self):
        return {"model_id": "falso"}

    async def structured_output(self, *_, **__):
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **_):
        self.turn += 1
        self.seen_tools = [t["name"] for t in tool_specs or []]
        yield {"messageStart": {"role": "assistant"}}
        if self.block:
            for _ in range(200):
                await asyncio.sleep(0.05)
                yield {"contentBlockDelta": {"delta": {"text": "."}}}
        elif self.turn == 1:
            yield {
                "contentBlockStart": {
                    "start": {"toolUse": {"name": "read", "toolUseId": "t1"}},
                }
            }
            args = json.dumps({"path": "nota.txt"})
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": args}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            yield {"metadata": {"usage": dict(USAGE), "metrics": {"latencyMs": 1}}}
            return
        else:
            self.tool_result = json.dumps(messages[-1]["content"], ensure_ascii=False)
            yield {"contentBlockDelta": {"delta": {"text": json.dumps(VERDICT)}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": dict(USAGE), "metrics": {"latencyMs": 1}}}


@pytest.fixture
def con_modelo(monkeypatch):
    """La fábrica real usa `create_harness`; solo se sustituye el modelo por el falso."""

    def preparar(model):
        real = strands_harness.create_harness

        def create_harness(**kwargs):
            kwargs["model"] = model
            return real(**kwargs)

        monkeypatch.setattr(strands_harness, "create_harness", create_harness)
        return model

    return preparar


def _request(cwd, **overrides):
    role = default_roles()["checker"]
    values = dict(
        role="checker",
        prompt="revisa",
        system_prompt="Eres el checker.",
        cwd=cwd,
        model="opus",
        permission_mode=role.permission_mode,
        allowed_tools=role.allowed_tools,
        denied_tools=role.denied_tools,
        max_budget_usd=1.0,
        timeout_s=30,
        json_schema=CHECKER_VERDICT_SCHEMA,
    )
    values.update(overrides)
    return AgentRequest(**values)


def test_invocacion_real_con_herramienta(tmp_path, monkeypatch, con_modelo, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nota.txt").write_text("contenido de la nota\n")
    model = con_modelo(ScriptedModel())
    result = StrandsRunner(StrandsConfig()).run(_request(tmp_path))
    assert result.ok, result.error
    assert result.output == VERDICT
    # Lista exacta: solo las confinadas. Una herramienta nueva de Strands hará fallar esto.
    assert model.seen_tools == ["read", "glob", "grep"]
    assert "contenido de la nota" in model.tool_result  # la herramienta real se ejecutó
    assert result.input_tokens == 2000 and result.output_tokens == 200
    assert result.num_turns == 2
    assert result.cost_usd == pytest.approx((2000 * 4 + 200 * 20) / 1_000_000)
    assert capsys.readouterr().out == ""  # Strands no imprime en stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["nota.txt"]  # sin `.agent/`


def test_resultado_grande_se_trunca_sin_almacen_ni_disco(tmp_path, monkeypatch, con_modelo):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nota.txt").write_text("linea de relleno bastante larga\n" * 1900)
    model = con_modelo(ScriptedModel())
    result = StrandsRunner(StrandsConfig()).run(_request(tmp_path))
    assert result.ok, result.error
    assert result.output == VERDICT
    assert len(model.tool_result) < 1900 * 30  # el gestor de contexto lo recortó
    assert sorted(p.name for p in tmp_path.iterdir()) == ["nota.txt"]


def test_herramienta_fuera_del_confinamiento_es_un_error_para_el_agente(
    tmp_path, monkeypatch, con_modelo
):
    monkeypatch.chdir(tmp_path)
    model = con_modelo(ScriptedModel())  # lee nota.txt, que aquí no existe
    result = StrandsRunner(StrandsConfig()).run(_request(tmp_path))
    assert result.ok, result.error  # el error vuelve al modelo; el runner no se detiene
    assert "no existe" in model.tool_result


def test_tiempo_agotado_a_mitad_del_stream(tmp_path, monkeypatch, con_modelo):
    monkeypatch.chdir(tmp_path)
    con_modelo(ScriptedModel(block=True))
    result = StrandsRunner(StrandsConfig()).run(_request(tmp_path, timeout_s=0.3))
    assert not result.ok and "tiempo agotado" in result.error
    # El uso registrado está a ceros: el coste es la estimación del turno cortado, no 0.
    assert result.input_tokens == 0
    assert result.cost_usd >= IN_FLIGHT_OUTPUT_TOKENS * 20 / 1_000_000
    assert result.cost_usd < 1.0
