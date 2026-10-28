"""Escenarios de `goal-loop`: retrabajo desde una ejecución anterior."""

from conftest import make_loop_repo, write_goal

import factory.cli as cli
from factory.agents.fake import FakeRunner, FakeStep, maker_done
from factory.cli import main
from factory.config import load_config
from factory.engine import LoopEngine
from factory.goal import load_goal
from factory.inbox import Inbox
from factory.state import RunStore
from factory.util import git

ASK = FakeStep(
    output={"status": "needs_human", "summary": "duda", "question": "¿Archivo nuevo o existente?"},
    edits={"parcial.txt": "trabajo del padre\n"},
)


def _blocked_parent(tmp_path):
    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(write_goal(root, files=("a.txt",)), config.loop)
    parent = LoopEngine(config, goal, FakeRunner(maker=[ASK]), echo=lambda _: None).run()
    assert parent.status == "blocked"
    return root, config, parent


def _rework(root, run_id, *extra):
    return main(["--root", str(root), "goal", "rework", run_id, *extra])


def test_hija_parte_de_la_punta_del_padre_con_base_original(tmp_path, monkeypatch):
    root, config, parent = _blocked_parent(tmp_path)
    parent_tip = git(root, "rev-parse", parent.branch)
    runner = FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    monkeypatch.setattr(cli, "make_runner", lambda _c: runner)
    assert _rework(root, parent.run_id, "--answer", "usa un archivo nuevo") == 0
    child = next(s for s in RunStore(config.state_path).list_runs() if s.parent_run_id)
    assert child.parent_run_id == parent.run_id
    assert child.start_commit == parent_tip and child.base_commit == parent.base_commit
    assert child.branch != parent.branch
    assert git(root, "rev-parse", parent.branch) == parent_tip  # la rama padre queda intacta
    assert git(root, "show", f"{child.branch}:parcial.txt") == "trabajo del padre"


def test_retrabajo_de_una_ejecucion_bloqueada(tmp_path, monkeypatch):
    root, config, parent = _blocked_parent(tmp_path)
    runner = FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    monkeypatch.setattr(cli, "make_runner", lambda _c: runner)
    assert _rework(root, parent.run_id, "--answer", "usa un archivo nuevo") == 0
    first = runner.calls_for("maker")[0].prompt
    assert "RESPUESTA HUMANA" in first and "usa un archivo nuevo" in first
    assert "¿Archivo nuevo o existente?" in first
    checker = runner.calls_for("checker")[0].prompt
    assert "+trabajo del padre" in checker  # el diff acumulado incluye el trabajo del padre


def test_retrabajo_de_una_ejecucion_completada(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(write_goal(root), config.loop)
    done = LoopEngine(
        config, goal, FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})]), echo=lambda _: None
    ).run()
    monkeypatch.setattr(cli, "make_runner", lambda _c: (_ for _ in ()).throw(AssertionError()))
    assert _rework(root, done.run_id, "--answer", "x") == 2
    assert f"factory land {done.run_id}" in capsys.readouterr().err
    assert len(RunStore(config.state_path).list_runs()) == 1


def test_retrabajo_sin_respuesta(tmp_path, capsys):
    root, config, parent = _blocked_parent(tmp_path)
    assert _rework(root, parent.run_id) == 2
    assert "respuesta humana es obligatoria" in capsys.readouterr().err
    assert len(RunStore(config.state_path).list_runs()) == 1


def test_la_entrada_de_la_bandeja_de_la_ejecucion_padre(tmp_path, monkeypatch):
    root, config, parent = _blocked_parent(tmp_path)
    monkeypatch.setattr(
        cli, "make_runner", lambda _c: FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    )
    answer = tmp_path / "respuesta.md"
    answer.write_text("usa un archivo nuevo\n")
    assert _rework(root, parent.run_id, "--answer-file", str(answer)) == 0
    entry = next(e for e in Inbox(config.state_path).entries() if e.id == parent.run_id)
    child = next(s for s in RunStore(config.state_path).list_runs() if s.parent_run_id)
    assert entry.status == "reviewed" and entry.resolution == f"retrabajo → {child.run_id}"


def test_ejecucion_inexistente(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    assert _rework(root, "no-existe", "--answer", "x") == 2
    assert "No existe la ejecución" in capsys.readouterr().err
