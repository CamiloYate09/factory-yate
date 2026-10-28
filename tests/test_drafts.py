"""Escenarios de `request-intake`: los borradores no se ejecutan y la promoción es explícita."""

import pytest
from conftest import make_loop_repo

import factory.cli as cli
from factory.agents.fake import FakeRunner
from factory.cli import main
from factory.config import load_config
from factory.engine import LoopEngine
from factory.goal import GoalError, load_goal
from factory.requests import RequestStore

DRAFT = """---
id: {id}
objective: Crear el marcador
mode: {mode}
status: draft
request: {request}
risk: low
surfaces: []
acceptance:
  - name: marca
    run: touch marcador-ejecutado
  - name: inexistente
    run: herramienta-que-no-existe --check
---
Cuerpo del borrador.
"""


def _draft(root, goal_id="x", mode="finite", request=""):
    path = root / "goals" / "drafts" / f"{goal_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DRAFT.format(id=goal_id, mode=mode, request=request))
    return path


def _no_runner(_config):
    raise AssertionError("un borrador no debe invocar agentes")


def test_ejecutar_un_borrador_con_goal_run(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    monkeypatch.setattr(cli, "make_runner", _no_runner)
    assert main(["--root", str(root), "goal", "run", str(_draft(root))]) == 2
    assert "factory goal promote" in capsys.readouterr().err
    assert not (root / "marcador-ejecutado").exists()


def test_ejecutar_un_borrador_con_tick(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    monkeypatch.setattr(cli, "make_runner", _no_runner)
    assert main(["--root", str(root), "tick", str(_draft(root, mode="monitor"))]) == 2
    assert "BORRADOR" in capsys.readouterr().err
    assert not (root / "marcador-ejecutado").exists()


def test_el_motor_tambien_rechaza_borradores(tmp_path):
    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(_draft(root), config.loop)
    with pytest.raises(GoalError, match="BORRADOR"):
        LoopEngine(config, goal, FakeRunner(), echo=lambda _: None).run()
    assert not (root / "marcador-ejecutado").exists()


def test_promocion_sin_confirmacion(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    draft = _draft(root)
    before = draft.read_text()
    assert main(["--root", str(root), "goal", "promote", str(draft)]) == 0
    out = capsys.readouterr().out
    assert "marca: touch marcador-ejecutado" in out and "Nada cambió" in out
    assert "AVISO: inexistente: no se encuentra `herramienta-que-no-existe`" in out
    assert not (root / "goals" / "x.md").exists() and draft.read_text() == before
    assert not (root / "marcador-ejecutado").exists()


def test_promocion_confirmada(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    store = RequestStore(load_config(root).state_path)
    req = store.create("crea el marcador")
    (store.dir(req.id) / "intake.md").write_text("DECISION: ACCEPT\n\nok\n")
    draft = _draft(root, request=req.id)
    req.draft = str(draft.relative_to(root))
    from factory.requests import advance

    advance(store, req, "accepted", root=root)
    assert main(["--root", str(root), "goal", "promote", str(draft), "--yes"]) == 0
    promoted = root / "goals" / "x.md"
    assert promoted.exists() and "status: draft" not in promoted.read_text()
    assert "request: " + req.id in promoted.read_text()
    assert store.load(req.id).stage == "promoted"
    capsys.readouterr()
    assert main(["--root", str(root), "goal", "run", str(promoted), "--dry-run"]) == 0
    assert "Simulación" in capsys.readouterr().out
    assert main(["--root", str(root), "goal", "promote", str(draft), "--yes"]) == 2
    assert "no se sobrescribe" in capsys.readouterr().err


def test_promover_algo_que_no_es_borrador(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    goal = root / "goals" / "normal.md"
    goal.parent.mkdir(exist_ok=True)
    goal.write_text(
        DRAFT.format(id="normal", mode="finite", request="").replace("status: draft\n", "")
    )
    assert main(["--root", str(root), "goal", "promote", str(goal), "--yes"]) == 2
    assert "no es un borrador" in capsys.readouterr().err
