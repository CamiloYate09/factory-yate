"""Escenarios de `goal-loop`: configuración de rutas protegidas y liberación explícita."""

import pytest

from factory.config import LoopConfig, load_config
from factory.globs import matches
from factory.goal import GoalError, parse_goal_text
from factory.protection import CRITICAL_SAMPLES, STATIC_CRITICAL

BASE = """---
id: g
objective: o
acceptance:
  - name: check
    run: ./scripts/check.sh
scope:
  allow: ["**"]
{scope}---
cuerpo
"""


def _goal(scope=""):
    return parse_goal_text(BASE.format(scope=scope), LoopConfig())


@pytest.mark.parametrize(
    "pattern", ["factory.toml", "feature_list.json", "prompts/**", "prompts/maker.md", "**"]
)
def test_un_objetivo_intenta_liberar_un_archivo_critico(pattern):
    with pytest.raises(GoalError, match="no puede liberar archivos críticos"):
        _goal(f'  allow_modify: ["{pattern}"]\n')


def test_liberar_ruta_no_critica_es_valido():
    goal = _goal('  protected: ["src/core/**"]\n  allow_modify: ["tests/test_calc.py"]\n')
    assert goal.protected == ["src/core/**"]
    assert goal.allow_modify == ["tests/test_calc.py"]


def test_config_protected_paths(tmp_path):
    (tmp_path / "factory.toml").write_text('[loop]\nprotected_paths = ["tests/**"]\n')
    assert load_config(tmp_path).loop.protected_paths == ["tests/**"]
    assert load_config(tmp_path / "..").loop.protected_paths == []


def test_proteccion_efectiva_incluye_scripts_y_se_describe(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check.sh").write_text("#!/bin/sh\n")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "lint.sh").write_text("#!/bin/sh\n")
    text = BASE.format(scope='  allow_modify: ["tests/test_calc.py"]\n').replace(
        "    run: ./scripts/check.sh",
        "    run: ./scripts/check.sh\n  - name: lint\n    run: bash tools/lint.sh",
    )
    goal = parse_goal_text(text, LoopConfig())
    prot = goal.protection_for(tmp_path, ["tests/**"], "./scripts/check.sh")
    assert {"scripts/check.sh", "tools/lint.sh"} <= set(prot.critical)
    assert prot.is_protected("tests/test_x.py") and not prot.is_protected("tests/test_calc.py")
    assert prot.is_protected("factory.toml") and not prot.is_protected("src/a.py")
    text_out = goal.describe(prot)
    assert "Rutas protegidas (críticas, siempre):" in text_out and "scripts/check.sh" in text_out
    assert "Liberadas por el objetivo: tests/test_calc.py" in text_out


# ------------------------------------------------- definiciones del equipo (add-equipo-ideal)


@pytest.mark.parametrize("pattern", [".claude/skills/**", ".claude/agents/**", ".claude/**"])
def test_un_objetivo_intenta_liberar_las_skills(pattern):
    with pytest.raises(GoalError, match="no puede liberar archivos críticos del harness") as exc:
        _goal(f'  allow_modify: ["{pattern}"]\n')
    assert ".claude/agents/**" in str(exc.value) and ".claude/skills/**" in str(exc.value)


@pytest.mark.parametrize(
    "pattern",
    [
        ".claude/agents/qa.md",
        ".claude/skills/equipo/**",
        ".claude/skills/*/LICENSE",
        "prompts/checker.md",
        "**/SKILL.md",
        "**/maker.md",
    ],
)
def test_un_objetivo_intenta_liberar_un_agente_concreto_del_equipo(pattern):
    with pytest.raises(GoalError, match="no puede liberar archivos críticos del harness"):
        _goal(f'  allow_modify: ["{pattern}"]\n')


@pytest.mark.parametrize("pattern", ["./prompts/checker.md", "./.claude/agents/qa.md"])
def test_ruta_con_prefijo(pattern):
    with pytest.raises(GoalError, match="no puede liberar archivos críticos del harness"):
        _goal(f'  allow_modify: ["{pattern}"]\n')


def test_liberar_el_script_de_verificacion(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    goal = _goal('  allow_modify: ["scripts/check.sh"]\n')  # el criterio ejecuta ./scripts/check.sh
    prot = goal.protection_for(tmp_path, [], None)
    assert "scripts/check.sh" in prot.critical
    assert prot.is_protected("scripts/check.sh")
    assert "Liberadas por el objetivo: scripts/check.sh (sin efecto: crítico)" in prot.describe()


@pytest.mark.parametrize("pattern", [".claude/*/qa.md", "**/LICENSE", "**/*.cjs"])
def test_comodin_que_solapa_en_parte_con_un_critico(tmp_path, pattern):
    """La validación no lo detecta, pero no libera nada: los críticos se consultan primero."""
    goal = _goal(f'  allow_modify: ["{pattern}"]\n')
    assert goal.allow_modify == [pattern]
    prot = goal.protection_for(tmp_path, [], None)
    assert prot.released == [pattern]
    assert f"{pattern} (los críticos que cubra siguen protegidos)" in "\n".join(prot.describe())
    for critico in (
        ".claude/agents/qa.md",
        ".claude/skills/security-audit/LICENSE",
        ".claude/skills/security-audit/validate-findings.cjs",
    ):
        assert prot.is_protected(critico), critico


def test_cada_critico_estatico_tiene_una_muestra():
    for pattern in STATIC_CRITICAL:
        assert any(matches(sample, [pattern]) for sample in CRITICAL_SAMPLES), pattern


def test_las_definiciones_del_equipo_son_criticas(tmp_path):
    goal = _goal('  allow_modify: ["tests/test_calc.py"]\n')
    prot = goal.protection_for(tmp_path, [], None)
    assert {".claude/agents/**", ".claude/skills/**"} <= set(prot.critical)
    assert prot.is_protected(".claude/agents/qa.md")
    assert prot.is_protected(".claude/skills/equipo/SKILL.md")
    assert not prot.is_protected(".claude/agents-old/x.md")
    assert ".claude/agents/**, .claude/skills/**" in goal.describe(prot)


@pytest.mark.parametrize(
    "pattern", [".claude/settings.json", ".claude/hooks/**", ".claude/commands/opsx/apply.md"]
)
def test_un_objetivo_intenta_liberar_la_configuracion_de_claude_code(pattern):
    with pytest.raises(GoalError, match="no puede liberar archivos críticos del harness"):
        _goal(f'  allow_modify: ["{pattern}"]\n')


def test_la_configuracion_de_claude_code_es_critica(tmp_path):
    prot = _goal().protection_for(tmp_path, [], None)
    for path in (".claude/settings.json", ".claude/hooks/panel-hook.sh", ".claude/commands/x.md"):
        assert prot.is_protected(path), path
    assert not prot.is_protected(".claude/settings.local.json")
