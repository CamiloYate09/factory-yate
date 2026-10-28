"""El agente simulado reproduce guiones por ronda para probar el loop sin red ni coste."""

from factory.agents.base import AgentRequest
from factory.agents.fake import FakeRunner, FakeStep, finding, maker_done, verdict


def _req(tmp_path, role="maker"):
    return AgentRequest(
        role=role,
        prompt="p",
        system_prompt="s",
        cwd=tmp_path,
        model="sonnet",
        permission_mode="acceptEdits",
    )


def test_edita_archivos_y_devuelve_informe(tmp_path):
    runner = FakeRunner(maker=[maker_done("listo", **{"src/a.py": "x = 1\n"})])
    result = runner.run(_req(tmp_path))
    assert result.ok and result.output["status"] == "done"
    assert (tmp_path / "src" / "a.py").read_text() == "x = 1\n"
    assert result.model == "sonnet"


def test_borra_archivos(tmp_path):
    (tmp_path / "b.txt").write_text("x")
    FakeRunner(maker=[FakeStep(edits={"b.txt": None})]).run(_req(tmp_path))
    assert not (tmp_path / "b.txt").exists()


def test_guion_por_rol_y_repite_ultimo_paso(tmp_path):
    runner = FakeRunner(checker=[verdict("fail", finding("critical")), verdict("pass")])
    results = [runner.run(_req(tmp_path, "checker")).output["verdict"] for _ in range(3)]
    assert results == ["fail", "pass", "pass"]
    assert len(runner.calls_for("checker")) == 3


def test_simula_coste_error_y_timeout(tmp_path):
    runner = FakeRunner(
        maker=[
            FakeStep(cost_usd=0.5, input_tokens=9),
            FakeStep(error="boom"),
            FakeStep(timeout=True),
        ]
    )
    first = runner.run(_req(tmp_path))
    assert (first.cost_usd, first.input_tokens) == (0.5, 9)
    second = runner.run(_req(tmp_path))
    assert not second.ok and second.error == "boom"
    third = runner.run(_req(tmp_path))
    assert not third.ok and "tiempo" in third.error


def test_checker_que_intenta_escribir(tmp_path):
    runner = FakeRunner(
        checker=[FakeStep(output={"verdict": "pass", "findings": []}, edits={"x": "1"})]
    )
    runner.run(_req(tmp_path, "checker"))
    assert (tmp_path / "x").exists()
