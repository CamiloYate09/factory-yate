"""Adaptador `claude -p`: argv por rol, parseo de salidas grabadas y errores accionables."""

import json
import stat
from pathlib import Path

import pytest

from factory.agents.base import AgentRequest
from factory.agents.claude_code import ClaudeCodeRunner, build_argv, parse_result

FIXTURES = Path(__file__).parent / "fixtures" / "claude"


def _req(tmp_path, **overrides):
    values = dict(
        role="checker",
        prompt="REVISA ESTO",
        system_prompt="Eres el checker",
        cwd=tmp_path,
        model="opus",
        permission_mode="dontAsk",
        allowed_tools=["Read", "Glob", "Grep"],
        denied_tools=["Edit", "Bash(git push:*)"],
        max_budget_usd=0.4,
        timeout_s=10,
        json_schema={"type": "object"},
    )
    values.update(overrides)
    return AgentRequest(**values)


def test_argv_por_rol(tmp_path):
    argv = build_argv(_req(tmp_path))
    assert argv[:2] == ["claude", "-p"]
    joined = " ".join(argv)
    for flag in (
        "--output-format json",
        "--no-session-persistence",
        "--model opus",
        "--permission-mode dontAsk",
        "--max-budget-usd 0.40",
        "--allowedTools Read,Glob,Grep",
        "--disallowedTools Edit,Bash(git push:*)",
        '--json-schema {"type":"object"}',
        "--append-system-prompt Eres el checker",
    ):
        assert flag in joined
    assert "REVISA ESTO" not in argv  # el prompt va por stdin
    assert "--resume" not in argv and "--continue" not in argv
    assert not any("dangerously" in a or "bypass" in a for a in argv)


def test_argv_rechaza_bypass(tmp_path):
    with pytest.raises(ValueError, match="prohibido"):
        build_argv(_req(tmp_path, permission_mode="bypassPermissions"))


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parsea_salida_real():
    result = parse_result(_fixture("plain_real.json"), "haiku")
    assert result.ok
    assert result.text == "`./scripts/check.sh`"
    assert result.cost_usd == pytest.approx(0.0034617, rel=1e-3)
    assert result.num_turns == 1
    assert result.input_tokens > 0 and result.output_tokens > 0
    assert result.permission_denials == []
    assert result.output is None


@pytest.mark.parametrize("name", ["structured_output.json", "verdict_in_result.json"])
def test_parsea_salida_estructurada(name):
    result = parse_result(_fixture(name), "opus")
    assert result.ok
    assert result.output["verdict"] == "fail"
    assert result.output["findings"][0]["severity"] == "critical"
    assert result.model == "claude-sonnet-5-5"  # modelo efectivo según modelUsage


def test_error_del_agente():
    result = parse_result(_fixture("error_budget.json"), "haiku")
    assert not result.ok
    assert "error_max_budget_usd" in result.error


def test_salida_ilegible():
    result = parse_result("esto no es json", "haiku")
    assert not result.ok and "ilegible" in result.error


def _fake_cli(tmp_path, body):
    script = tmp_path / "fake-claude"
    script.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_invoca_cli_con_prompt_por_stdin(tmp_path):
    fixture = FIXTURES / "structured_output.json"
    cli = _fake_cli(tmp_path, f'cat > "{tmp_path}/stdin.txt"\ncat "{fixture}"\n')
    result = ClaudeCodeRunner(cli).run(_req(tmp_path))
    assert result.ok and result.output["verdict"] == "fail"
    assert (tmp_path / "stdin.txt").read_text() == "REVISA ESTO"


def test_cli_ausente_mensaje_accionable(tmp_path):
    result = ClaudeCodeRunner(str(tmp_path / "no-existe")).run(_req(tmp_path))
    assert not result.ok
    assert "No se encontró el ejecutable" in result.error and "claude --version" in result.error


def test_timeout(tmp_path):
    cli = _fake_cli(tmp_path, "sleep 5\n")
    result = ClaudeCodeRunner(cli).run(_req(tmp_path, timeout_s=0.3))
    assert not result.ok and "tiempo agotado" in result.error


def test_codigo_distinto_de_cero(tmp_path):
    payload = json.dumps({"result": "x", "is_error": False, "subtype": "success"})
    cli = _fake_cli(tmp_path, f"echo '{payload}'\necho 'fallo raro' >&2\nexit 3\n")
    result = ClaudeCodeRunner(cli).run(_req(tmp_path))
    assert not result.ok and "código 3" in result.error and "fallo raro" in result.error
