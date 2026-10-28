"""Escenario de `scheduled-loop`: programación externa explícita (no modifica el sistema)."""

import os
import subprocess

import pytest
from conftest import make_loop_repo, write_goal

from factory.cli import main
from factory.schedule import ScheduleError, parse_interval


@pytest.fixture
def no_system_changes(monkeypatch):
    def guard(*args, **_kwargs):
        text = " ".join(map(str, args[0] if args and isinstance(args[0], list) else args))
        if "crontab" in text or "launchctl" in text:
            raise AssertionError(f"no debe modificar el sistema: {text}")
        return real_run(*args, **_kwargs)

    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", guard)
    monkeypatch.setattr(os, "system", lambda cmd: (_ for _ in ()).throw(AssertionError(cmd)))


def test_obtener_configuracion_de_cron(tmp_path, capsys, no_system_changes):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root, extra="mode: monitor\n")
    assert main(["--root", str(root), "schedule", str(goal), "--every", "30m"]) == 0
    out = capsys.readouterr().out
    assert "*/30 * * * * cd " in out and f'tick "{goal}"' in out
    assert "<key>StartInterval</key><integer>1800</integer>" in out
    assert "/loop 30m Ejecuta" in out and "goals/demo.md" in out
    assert "No se ha instalado nada" in out


@pytest.mark.parametrize(
    "text, cron",
    [("15m", "*/15 * * * *"), ("2h", "0 */2 * * *"), ("1d", "0 9 * * *")],
)
def test_intervalos(text, cron):
    from factory.schedule import cron_expression

    assert cron_expression(parse_interval(text)) == cron


@pytest.mark.parametrize("text", ["30", "0m", "90m", "2d", "cada hora"])
def test_intervalos_invalidos(text):
    with pytest.raises(ScheduleError):
        parse_interval(text)


def test_solo_objetivos_de_vigilancia(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    goal = write_goal(root)
    assert main(["--root", str(root), "schedule", str(goal), "--every", "1h"]) == 2
    assert "vigilancia" in capsys.readouterr().err
