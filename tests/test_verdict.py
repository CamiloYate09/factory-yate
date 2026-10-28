"""Escenarios de `maker-checker-loop`: veredicto estructurado con evidencia."""

import pytest

from factory.agents.fake import finding
from factory.schemas import (
    CHECKER_VERDICT_SCHEMA,
    MAKER_REPORT_SCHEMA,
    parse_maker_report,
    parse_verdict,
)


def test_veredicto_valido():
    verdict, errors = parse_verdict({"verdict": "fail", "findings": [finding("critical")]})
    assert errors == []
    assert verdict.verdict == "fail" and not verdict.approves
    assert verdict.blocking[0].severity == "critical"


@pytest.mark.parametrize(
    "data",
    [
        "no soy un objeto",
        {"verdict": "ok", "findings": []},
        {"verdict": "pass"},
        {"verdict": "pass", "findings": "ninguno"},
        {"verdict": "pass", "findings": [{**finding(), "severity": "grave"}]},
    ],
)
def test_veredicto_malformado(data):
    verdict, errors = parse_verdict(data)
    assert verdict is None and errors


@pytest.mark.parametrize("missing", ["location", "evidence"])
def test_hallazgo_sin_evidencia_o_ubicacion(missing):
    item = finding("minor")
    item[missing] = "  "
    verdict, errors = parse_verdict({"verdict": "pass_with_minor", "findings": [item]})
    assert verdict is None
    assert any(missing in e for e in errors)


@pytest.mark.parametrize(
    "result, severities, approves",
    [
        ("pass", [], True),
        ("pass_with_minor", ["minor"], True),
        ("pass_with_minor", ["medium"], False),
        ("pass", ["critical"], False),
        ("fail", [], False),
    ],
)
def test_aprobacion(result, severities, approves):
    verdict, _ = parse_verdict({"verdict": result, "findings": [finding(s) for s in severities]})
    assert verdict.approves is approves


def test_informe_del_maker():
    report, errors = parse_maker_report(
        {"status": "needs_human", "summary": "duda", "question": "¿A o B?"}
    )
    assert errors == [] and report.question == "¿A o B?"
    assert parse_maker_report({"status": "listo", "summary": 1})[0] is None


def test_esquemas_exigen_evidencia():
    assert CHECKER_VERDICT_SCHEMA["required"] == ["verdict", "findings"]
    item = CHECKER_VERDICT_SCHEMA["properties"]["findings"]["items"]
    assert {"location", "evidence"} <= set(item["required"])
    assert MAKER_REPORT_SCHEMA["properties"]["status"]["enum"] == [
        "done",
        "in_progress",
        "needs_human",
    ]


def test_prompts_del_repo_mencionan_tests_debilitados():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    checker = (root / "prompts" / "checker.md").read_text(encoding="utf-8")
    assert "Tests debilitados" in checker and "diff acumulado" in checker
    maker = (root / "prompts" / "maker.md").read_text(encoding="utf-8")
    assert "needs_human" in maker
