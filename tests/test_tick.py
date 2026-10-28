"""Escenarios de `scheduled-loop`: tick con verificación previa sin coste."""

from conftest import make_loop_repo, write_goal

import factory.cli as cli
from factory.agents.fake import FakeRunner, maker_done
from factory.cli import main
from factory.inbox import Inbox
from factory.tick import TickStore


def _no_runner(_config):
    raise AssertionError("no debe invocarse ningún agente")


def test_todo_en_orden_noop_sin_agentes(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root, extra="mode: monitor\n", criteria="  - name: ok\n    run: 'true'\n")
    monkeypatch.setattr(cli, "make_runner", _no_runner)
    assert main(["--root", str(root), "tick", str(goal)]) == 0
    assert "tick 'demo': noop · coste 0.0000 USD" in capsys.readouterr().out
    [record] = TickStore(root / ".factory").read("demo")
    assert record.result == "noop" and record.cost_usd == 0


def test_se_detecta_un_fallo_y_lanza_ejecucion_acotada(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    (root / "factory.toml").write_text("[tick]\nmax_rounds = 2\nbudget_per_tick_usd = 1.5\n")
    goal = write_goal(root, extra="mode: monitor\n", max_rounds=8, budget=9)
    runner = FakeRunner(maker=[maker_done("arreglado", **{"a.txt": "1"})])
    monkeypatch.setattr(cli, "make_runner", lambda _config: runner)
    assert main(["--root", str(root), "tick", str(goal)]) == 0
    [record] = TickStore(root / ".factory").read("demo")
    assert record.result == "run" and record.run_id and record.run_status == "completed"
    request = runner.calls_for("maker")[0]
    assert "ronda 1 de 2" in request.prompt  # límites por tick, no los del goal
    assert request.max_budget_usd <= 1.5
    [entry] = Inbox(root / ".factory").pending()
    assert entry.origin == "tick" and entry.id == record.run_id


def test_objetivo_finito_programado_se_rechaza(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root)
    monkeypatch.setattr(cli, "make_runner", _no_runner)
    assert main(["--root", str(root), "tick", str(goal)]) == 2
    assert "factory goal run" in capsys.readouterr().err
    assert TickStore(root / ".factory").read("demo") == []
