"""Escenarios de `goal-loop`: `factory goal run` (simulación y sin integración automática)."""

import subprocess

import pytest
from conftest import init_git_repo, make_loop_repo, write_goal

import factory.cli as cli
from factory.agents.fake import FakeRunner, maker_done
from factory.cli import main
from factory.util import git


def _no_runner(_config):
    raise AssertionError("la simulación no debe crear ningún agente")


def test_simulacion_no_invoca_agentes_ni_crea_ramas(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root)
    monkeypatch.setattr(cli, "make_runner", _no_runner)
    assert main(["--root", str(root), "goal", "run", str(goal), "--dry-run"]) == 0
    out = capsys.readouterr().out
    for text in (
        "Límites efectivos:",
        "maker: modelo=sonnet",
        "checker: modelo=opus",
        "coste 0 USD",
    ):
        assert text in out
    assert "Bash(test -f a.txt)" in out
    assert git(root, "branch", "--list", "factory/*") == ""
    assert not (root / ".factory" / "runs").exists()
    assert not (tmp_path / "repo.factory-worktrees").exists()


def test_objetivo_completado_no_toca_main_ni_hace_push(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    remote = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    main_before = git(root, "rev-parse", "main")
    goal = write_goal(root)
    runner = FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    monkeypatch.setattr(cli, "make_runner", lambda _config: runner)
    assert main(["--root", str(root), "goal", "run", str(goal)]) == 0
    out = capsys.readouterr().out
    assert "Resultado: completed" in out and "factory inbox list" in out
    assert git(root, "rev-parse", "main") == main_before
    assert not (root / "a.txt").exists()
    assert git(root, "ls-remote", "origin") == ""
    [branch] = git(root, "branch", "--list", "factory/*").split()
    assert git(root, "show", f"{branch}:a.txt") == "1"


@pytest.mark.parametrize(
    "maker, code",
    [
        ([maker_done("nada")], 3),  # stalled
        ([maker_done("x", **{"a.txt": "1"})], 0),
    ],
)
def test_codigo_de_salida_segun_resultado(tmp_path, monkeypatch, maker, code):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root, max_rounds=5, no_progress=3)
    monkeypatch.setattr(cli, "make_runner", lambda _config: FakeRunner(maker=maker))
    assert main(["--root", str(root), "goal", "run", str(goal)]) == code


def test_repo_sin_commits(tmp_path, monkeypatch, capsys):
    root = init_git_repo(tmp_path / "repo", commit=False)
    (root / "prompts").mkdir()
    for role in ("maker", "checker"):
        (root / "prompts" / f"{role}.md").write_text("x")
    goal = write_goal(root)
    monkeypatch.setattr(cli, "make_runner", lambda _config: FakeRunner())
    assert main(["--root", str(root), "goal", "run", str(goal)]) == 2
    assert "commit inicial" in capsys.readouterr().err


def test_objetivo_de_vigilancia_se_rechaza(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root, extra="mode: monitor\n")
    assert main(["--root", str(root), "goal", "run", str(goal), "--dry-run"]) == 2
    assert "factory tick" in capsys.readouterr().err
