"""Escenario de `scheduled-loop`: registro de ticks e integración en `factory status`."""

from conftest import make_loop_repo, write_goal

import factory.cli as cli
from factory.cli import main
from factory.tick import TickStore


def test_historial_de_vigilancia(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root, extra="mode: monitor\n", criteria="  - name: ok\n    run: 'true'\n")
    monkeypatch.setattr(cli, "make_runner", lambda _c: None)
    for _ in range(4):  # p. ej. cada 30 min durante dos horas
        main(["--root", str(root), "tick", str(goal)])
    records = TickStore(root / ".factory").read("demo")
    assert len(records) == 4
    assert all(r.result == "noop" and r.cost_usd == 0 and r.ts for r in records)
    capsys.readouterr()
    main(["--root", str(root), "status"])
    out = capsys.readouterr().out
    assert "Vigilancia (ticks):" in out
    assert "demo: 4 tick(s)" in out and "noop=4" in out and "coste 0.0000 USD" in out
