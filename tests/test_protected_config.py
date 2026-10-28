"""Escenarios de `goal-loop`: configuración de rutas protegidas y liberación explícita."""

import pytest

from factory.config import LoopConfig, load_config
from factory.goal import GoalError, parse_goal_text

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
