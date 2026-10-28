"""Escenarios de `scheduled-loop`: exclusión mutua entre ticks."""

import json
import os
import time

from conftest import make_loop_repo, write_goal

import factory.cli as cli
from factory.cli import main
from factory.tick import TickStore


def _monitor_ok(root):
    return write_goal(root, extra="mode: monitor\n", criteria="  - name: ok\n    run: 'true'\n")


def _lock(root, pid, started):
    path = root / ".factory" / "locks" / "demo.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "started": started}))
    return path


def _fail(_config):
    raise AssertionError("no debe invocarse ningún agente")


def test_tick_solapado_se_omite(tmp_path, monkeypatch, capsys):
    root = make_loop_repo(tmp_path)
    goal = _monitor_ok(root)
    lock = _lock(root, os.getpid(), time.time())
    monkeypatch.setattr(cli, "make_runner", _fail)
    assert main(["--root", str(root), "tick", str(goal)]) == 0
    [record] = TickStore(root / ".factory").read("demo")
    assert record.result == "skipped" and "otro tick en curso" in record.detail
    assert lock.exists()  # el bloqueo ajeno no se toca


def test_bloqueo_de_proceso_muerto_se_recupera(tmp_path, monkeypatch):
    root = make_loop_repo(tmp_path)
    goal = _monitor_ok(root)
    lock = _lock(root, 999_999, time.time())
    monkeypatch.setattr(cli, "make_runner", _fail)
    assert main(["--root", str(root), "tick", str(goal)]) == 0
    [record] = TickStore(root / ".factory").read("demo")
    assert record.result == "noop" and "bloqueo obsoleto recuperado" in record.detail
    assert not lock.exists()  # liberado al terminar


def test_bloqueo_demasiado_antiguo_se_recupera(tmp_path, monkeypatch):
    root = make_loop_repo(tmp_path)
    goal = _monitor_ok(root)
    _lock(root, os.getpid(), time.time() - 10 * 3600)
    monkeypatch.setattr(cli, "make_runner", _fail)
    main(["--root", str(root), "tick", str(goal)])
    assert TickStore(root / ".factory").read("demo")[0].result == "noop"


def test_bloqueo_vacio_y_reciente_cuenta_como_ocupado(tmp_path):
    store = TickStore(tmp_path / ".factory")
    path = store.lock_path("demo")
    path.parent.mkdir(parents=True)
    path.write_text("")  # otro proceso acaba de crearlo y aún no escribió su contenido
    acquired, detail = store.acquire("demo", stale_after_s=3600)
    assert not acquired and "en curso" in detail


def test_pid_invalido_no_cuenta_como_vivo():
    from factory.tick import _alive

    assert not _alive(-1) and not _alive(0)


def test_solo_un_proceso_gana_el_bloqueo(tmp_path):
    import subprocess
    import sys

    code = (
        "import sys, time; from pathlib import Path; from factory.tick import TickStore; "
        f"ok, _ = TickStore(Path({str(tmp_path / '.factory')!r})).acquire('demo', 3600); "
        "print(int(ok), flush=True); time.sleep(2)"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        for _ in range(8)
    ]
    results = [int(p.communicate()[0].strip()) for p in procs]
    assert sum(results) == 1


def test_release_solo_libera_el_bloqueo_propio(tmp_path):
    store = TickStore(tmp_path / ".factory")
    path = _lock(tmp_path / "x", 999_999, time.time())
    target = store.lock_path("demo")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(path.read_text())
    store.release("demo")
    assert target.exists()
