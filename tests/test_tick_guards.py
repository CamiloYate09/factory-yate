"""Escenarios de `scheduled-loop`: trabajo pendiente, presupuesto diario y cortacircuitos."""

import json

from conftest import make_loop_repo, write_goal

import factory.cli as cli
from factory.agents.fake import FakeRunner, maker_done
from factory.cli import main
from factory.inbox import Inbox
from factory.tick import TickStore


def _setup(tmp_path, monkeypatch, toml="[tick]\nmax_rounds = 1\n"):
    root = make_loop_repo(tmp_path)
    (root / "factory.toml").write_text(toml)
    goal = write_goal(root, extra="mode: monitor\n")
    runner = FakeRunner(maker=[maker_done("no lo arreglo")])
    monkeypatch.setattr(cli, "make_runner", lambda _config: runner)
    return root, goal, runner


def _tick(root, goal):
    return main(["--root", str(root), "tick", str(goal)])


def _results(root):
    return [r.result for r in TickStore(root / ".factory").read("demo")]


def test_rama_sin_revisar_no_duplica_trabajo(tmp_path, monkeypatch):
    root, goal, runner = _setup(tmp_path, monkeypatch)
    _tick(root, goal)
    calls = len(runner.calls)
    assert _tick(root, goal) == 1
    assert _results(root) == ["run", "awaiting_review"]
    assert len(runner.calls) == calls
    last = TickStore(root / ".factory").read("demo")[-1]
    assert Inbox(root / ".factory").pending()[0].id in last.detail


def test_presupuesto_diario_agotado(tmp_path, monkeypatch):
    root, goal, runner = _setup(tmp_path, monkeypatch, "[tick]\ndaily_budget_usd = 1.0\n")
    store = TickStore(root / ".factory")
    store.add_spend("demo", 1.0)
    assert _tick(root, goal) == 1
    assert _results(root) == ["budget_exhausted"] and runner.calls == []


def test_fallos_repetidos_abren_el_cortacircuitos_y_escalan(tmp_path, monkeypatch):
    root, goal, runner = _setup(
        tmp_path, monkeypatch, "[tick]\nmax_rounds = 1\ncircuit_after = 2\n"
    )
    inbox = Inbox(root / ".factory")
    for _ in range(2):
        _tick(root, goal)
        for entry in inbox.pending_for("demo", origin="tick"):
            inbox.ack(entry.id)  # el humano revisa, pero el problema persiste
    breaker = TickStore(root / ".factory").breaker("demo")
    assert breaker["open"] and breaker["failures"] == 2
    [escalation] = [e for e in inbox.pending() if e.kind == "escalation"]
    assert "--reset-breaker" in escalation.body
    calls = len(runner.calls)
    assert _tick(root, goal) == 1
    assert _results(root)[-1] == "circuit_open" and len(runner.calls) == calls


def test_restablecimiento(tmp_path, monkeypatch, capsys):
    root, goal, runner = _setup(tmp_path, monkeypatch)
    store = TickStore(root / ".factory")
    store.save_breaker("demo", {"open": True, "failures": 3})
    assert main(["--root", str(root), "tick", str(goal), "--reset-breaker"]) == 0
    assert "restablecido" in capsys.readouterr().out
    _tick(root, goal)
    assert _results(root) == ["run"] and runner.calls


def test_gasto_del_dia_se_acumula(tmp_path, monkeypatch):
    root, goal, runner = _setup(tmp_path, monkeypatch)
    _tick(root, goal)
    spend = json.loads(TickStore(root / ".factory").spend_path().read_text())
    assert spend["demo"] > 0


def test_error_del_motor_se_registra_con_gasto_y_cortacircuitos(tmp_path, monkeypatch):
    from factory.agents.fake import FakeStep

    root, goal, _ = _setup(tmp_path, monkeypatch)

    def boom(_request):
        raise RuntimeError("disco lleno")

    runner = FakeRunner(
        maker=[FakeStep(output={"status": "done", "summary": "x"}, cost_usd=0.25)],
        checker=[FakeStep(action=boom)],
    )
    monkeypatch.setattr(cli, "make_runner", lambda _config: runner)
    assert _tick(root, goal) == 1
    [record] = TickStore(root / ".factory").read("demo")
    assert record.result == "run" and record.run_status == "error"
    assert "disco lleno" in record.detail and record.cost_usd >= 0.25
    store = TickStore(root / ".factory")
    assert store.spent_today("demo") >= 0.25
    assert store.breaker("demo")["failures"] == 1
