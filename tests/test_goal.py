"""Escenarios de `goal-loop`: definición del objetivo y valores por defecto acotados."""

import re
from pathlib import Path

import pytest

from factory.cli import main
from factory.config import LoopConfig
from factory.goal import GoalError, glob_to_regex, load_goal, out_of_scope, parse_goal_text

ROOT = Path(__file__).resolve().parents[1]

VALID = """---
id: cobertura
objective: Subir la cobertura del módulo x
acceptance:
  - name: tests
    run: python -m pytest -q
scope:
  allow: ["src/**", "tests/**"]
  deny: ["src/factory/cli.py"]
stop:
  max_rounds: 4
  max_budget_usd: 1.5
---
Cuerpo con la metodología.
"""


def test_objetivo_valido(tmp_path, capsys):
    path = tmp_path / "cobertura.md"
    path.write_text(VALID, encoding="utf-8")
    assert main(["--root", str(tmp_path), "goal", "validate", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Objetivo 'cobertura' (finite): Subir la cobertura del módulo x" in out
    assert "tests: python -m pytest -q" in out
    assert "max_rounds = 4" in out
    assert "no_progress_rounds = 3 (por defecto)" in out
    assert "Objetivo válido." in out


def test_criterios_no_verificables(tmp_path, capsys):
    text = VALID.replace("    run: python -m pytest -q\n", "")
    path = tmp_path / "g.md"
    path.write_text(text, encoding="utf-8")
    assert main(["--root", str(tmp_path), "goal", "validate", str(path)]) == 2
    assert "verificable por máquina" in capsys.readouterr().err


def test_sin_acceptance(tmp_path):
    text = re.sub(r"acceptance:\n(  .*\n)+", "", VALID)
    with pytest.raises(GoalError, match="verificable por máquina"):
        parse_goal_text(text, LoopConfig())


def test_goal_sin_limites_usa_defaults_finitos():
    text = re.sub(r"stop:\n(  .*\n)+", "", VALID)
    defaults = LoopConfig()
    goal = parse_goal_text(text, defaults)
    assert goal.stop.max_rounds == defaults.max_rounds
    assert goal.stop.max_budget_usd == defaults.max_budget_usd
    assert set(goal.defaults_applied) == {
        "max_rounds",
        "max_budget_usd",
        "no_progress_rounds",
        "consecutive_passes",
        "round_timeout_min",
    }
    assert "(por defecto)" in goal.describe()


def test_feature_list_siempre_prohibido():
    goal = parse_goal_text(VALID, LoopConfig())
    assert "feature_list.json" in goal.deny
    assert out_of_scope(["feature_list.json"], goal) == ["feature_list.json"]


def test_alcance_permitido_y_prohibido():
    goal = parse_goal_text(VALID, LoopConfig())
    assert out_of_scope(["src/factory/goal.py", "tests/test_x.py"], goal) == []
    assert out_of_scope(["src/factory/cli.py"], goal) == ["src/factory/cli.py"]
    assert out_of_scope(["README.md"], goal) == ["README.md"]


@pytest.mark.parametrize(
    "pattern, path, expected",
    [
        ("src/**", "src/a/b.py", True),
        ("src/**", "srcx/a.py", False),
        ("**/*.md", "README.md", True),
        ("**/*.md", "docs/x/y.md", True),
        ("*.py", "a/b.py", False),
        ("docs/", "docs/a.md", True),
        ("./.github/**", ".github/workflows/ci.yml", True),
        ("tests/test_?.py", "tests/test_a.py", True),
    ],
)
def test_globs(pattern, path, expected):
    assert bool(glob_to_regex(pattern).match(path)) is expected


@pytest.mark.parametrize(
    "mutation, match",
    [
        (lambda t: t.replace("---\nid", "id", 1), "frontmatter"),
        (lambda t: t.replace("id: cobertura", "id: Cobertura X"), "inválido"),
        (lambda t: t.replace("objective: Subir la cobertura del módulo x\n", ""), "objective"),
        (lambda t: t.replace("max_rounds: 4", "max_rounds: 0"), "mayor que 0"),
        (lambda t: t.replace("max_rounds: 4", "max_rounds: 2.5"), "entero"),
        (lambda t: t.replace("id: cobertura", "id: cobertura\nmode: forever"), "mode"),
        (lambda t: t.replace("id: cobertura", "id: cobertura\nextra: 1"), "desconocidas"),
        (
            lambda t: t.replace(
                "id: cobertura", "id: c\nroles:\n  maker:\n    permission_mode: bypassPermissions"
            ),
            "prohibido",
        ),
    ],
)
def test_goal_invalidos(mutation, match):
    with pytest.raises(GoalError, match=match):
        parse_goal_text(mutation(VALID), LoopConfig())


def test_override_de_rol():
    from factory.config import default_roles

    text = VALID.replace("id: cobertura", "id: cobertura\nroles:\n  maker: {model: haiku}")
    goal = parse_goal_text(text, LoopConfig())
    base = default_roles()["maker"]
    assert goal.role("maker", base).model == "haiku"
    assert base.model == "sonnet"


def test_plantilla_del_repo_valida():
    goal = load_goal(ROOT / "goals" / "_template.md", LoopConfig())
    assert goal.mode == "finite"
    assert [c.name for c in goal.acceptance] == ["tests", "lint"]


def test_ejemplo_documentado_en_loops_md_valida():
    text = (ROOT / "docs" / "harness" / "loops.md").read_text(encoding="utf-8")
    block = text.split("<!-- ejemplo-goal", 1)[1].split("```markdown\n", 1)[1].split("\n```", 1)[0]
    goal = parse_goal_text(block + "\n", LoopConfig())
    assert goal.id == "validacion-config"
    assert goal.feature == "loop-config"
    assert "feature_list.json" in goal.deny
    from factory.config import default_roles

    assert goal.role("maker", default_roles()["maker"]).model == "sonnet"


def test_override_de_goal_no_puede_quitar_denegaciones():
    from factory.config import default_roles

    text = VALID.replace(
        "id: cobertura",
        "id: cobertura\nroles:\n  maker: {denied_tools: []}\n"
        "  checker: {allowed_tools: [Bash, Read], denied_tools: []}",
    )
    goal = parse_goal_text(text, LoopConfig())
    roles = default_roles()
    maker = goal.role("maker", roles["maker"])
    checker = goal.role("checker", roles["checker"])
    assert "Bash(git push:*)" in maker.denied_tools and "Bash(gh:*)" in maker.denied_tools
    assert checker.allowed_tools == ["Read"] and "Bash" in checker.denied_tools
