"""Renderizado de artefactos legibles por ronda (cabeceras CLAVE: valor)."""

from factory.artifacts import read_header, render_checks, render_decision, render_review
from factory.schemas import Finding, Verdict
from factory.state import RoundRecord, RunState
from factory.util import CommandResult
from factory.verify import Verification


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_checks_con_criterio_fallido_y_final_de_salida(tmp_path):
    record = RoundRecord(number=2, started="x", commit="abc123", decision="keep")
    salida = "x" * 5000 + "\nFAILED tests/test_a.py::test_b"
    verification = Verification(
        {
            "tests": CommandResult("pytest -q", 1, salida, 1.0),
            "lint": CommandResult("ruff", 0, "", 0.1),
        }
    )
    path = _write(tmp_path, "checks.md", render_checks(record, verification))
    head = read_header(path)
    assert head["GATE"] == "FAIL" and head["COMMIT"] == "abc123" and head["SCORE"] == "1/2"
    text = path.read_text()
    assert "❌ tests: `pytest -q` → código 1" in text and "FAILED tests/test_a.py::test_b" in text
    assert len(text) < 3000


def test_review_omitido_e_invalido(tmp_path):
    omitted = RoundRecord(number=1, started="x", checker_verdict="omitido", note="presupuesto")
    head = read_header(_write(tmp_path, "a.md", render_review(omitted, None)))
    assert head["VERDICT"] == "omitido"
    never = RoundRecord(number=1, started="x", decision="scope_revert")
    assert (
        read_header(_write(tmp_path, "b.md", render_review(never, None)))["VERDICT"]
        == "no_invocado"
    )


def test_review_con_hallazgos(tmp_path):
    verdict = Verdict(
        "fail", [Finding("critical", "a.py:3", "rompe", "evidencia", "arreglar")], "resumen"
    )
    record = RoundRecord(number=1, started="x", checker_verdict="fail", checker_model="opus")
    path = _write(tmp_path, "r.md", render_review(record, verdict))
    assert read_header(path) == {"VERDICT": "fail", "MODEL": "opus"}
    assert "[critical] a.py:3" in path.read_text()


def test_decision(tmp_path):
    state = RunState(
        run_id="r",
        goal_id="g",
        objective="o",
        status="blocked",
        stop_reason="duda",
        branch="factory/r",
        best_round=2,
        question="¿A o B?",
    )
    path = _write(tmp_path, "decision.md", render_decision(state))
    head = read_header(path)
    assert head["RESULT"] == "blocked" and head["REASON"] == "duda"
    assert head["BRANCH"] == "factory/r" and head["BEST_ROUND"] == "2"
    assert "¿A o B?" in path.read_text()


def test_tabla_documentada_coincide_con_lo_generado(tmp_path):
    from pathlib import Path

    doc = (
        Path(__file__).resolve().parents[1] / "docs" / "harness" / "observabilidad.md"
    ).read_text()
    table = doc.split("<!-- tabla-artefactos", 1)[1].split("\n\n", 1)[0]
    documented = {}
    for row in table.splitlines():
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) == 3 and cells[0].startswith("`"):
            name = cells[0].strip("`").split("/")[-1]
            keys = [k.strip() for k in cells[1].split(",")]
            documented[name] = (
                {k for k in keys if not k.startswith("[")},
                {k.strip("[]") for k in keys},
            )
    from factory.artifacts import render_maker

    record = RoundRecord(
        number=1,
        started="x",
        commit="c",
        decision="revert",
        reverted_to="b",
        maker_status="done",
        maker_model="m",
        checker_verdict="pass",
        checker_model="o",
    )
    verification = Verification({"t": CommandResult("true", 0, "", 0.1)})
    state = RunState(
        run_id="r",
        goal_id="g",
        objective="o",
        status="completed",
        stop_reason="ok",
        branch="factory/r",
        best_round=1,
        base_commit="b",
    )
    generated = {
        "maker.md": render_maker(record),
        "checks.md": render_checks(record, verification),
        "review.md": render_review(record, Verdict("pass", [], "")),
        "decision.md": render_decision(state),
    }
    assert set(documented) == set(generated)
    for name, text in generated.items():
        keys = set(read_header(_write(tmp_path, name, text)))
        required, allowed = documented[name]
        assert required <= keys <= allowed, name
