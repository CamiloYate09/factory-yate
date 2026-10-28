"""Escenarios de `loop-state`: registro acumulado de resultados y eventos de invocación."""

from factory.agents.base import AgentRequest, AgentResult
from factory.records import EventLog, append_result, read_results, truncate
from factory.util import CommandResult


def test_auditoria_posterior_seis_filas_sin_modificar_las_previas(tmp_path):
    for run in ("a", "b"):
        for n in (1, 2, 3):
            append_result(
                tmp_path,
                run_id=run,
                round=n,
                commit="abc",
                score=f"{n}/3",
                verdict="fail",
                decision="keep",
                cost_usd=0.1,
                duration_s=3,
                description=f"ronda\t{n}\ncon saltos",
            )
    first_lines = (tmp_path / "results.tsv").read_text().splitlines()
    rows = read_results(tmp_path)
    assert len(rows) == 6
    assert [(r["run_id"], r["round"]) for r in rows][:2] == [("a", "1"), ("a", "2")]
    assert rows[0]["description"] == "ronda 1 con saltos"
    append_result(tmp_path, run_id="c", round=1)
    assert (tmp_path / "results.tsv").read_text().splitlines()[: len(first_lines)] == first_lines


def test_diagnostico_de_una_ronda_fallida(tmp_path):
    log = EventLog(tmp_path / "run")
    request = AgentRequest(
        role="checker",
        prompt="p",
        system_prompt="s",
        cwd=tmp_path,
        model="opus",
        permission_mode="dontAsk",
    )
    result = AgentResult(
        ok=True,
        output={"verdict": "fail", "findings": []},
        cost_usd=0.2,
        input_tokens=5000,
        output_tokens=300,
        num_turns=3,
        model="claude-opus-5-5",
        permission_denials=[{"tool_name": "Bash"}],
    )
    log.command(2, "tests", CommandResult("pytest -q", 1, "x" * 5000 + "\nFAILED test_a", 1.5))
    log.agent(2, request, result)
    events = [e for e in log.read() if e["round"] == 2]
    command, agent = events
    assert command["type"] == "command" and command["exit_code"] == 1
    assert command["output"].endswith("FAILED test_a") and len(command["output"]) <= 2000
    assert agent["role"] == "checker" and agent["output"]["verdict"] == "fail"
    assert agent["model"] == "claude-opus-5-5" and agent["model_requested"] == "opus"
    assert agent["input_tokens"] == 5000 and agent["permission_denials"] == [{"tool_name": "Bash"}]


def test_truncate_conserva_el_final():
    assert truncate("abc", 10) == "abc"
    assert truncate("0123456789", 5) == "…6789"
