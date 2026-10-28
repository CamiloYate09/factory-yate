"""Escenarios de `run-landing`: integración asistida con `factory land`."""

import subprocess
from pathlib import Path

from conftest import make_loop_repo, write_goal

import factory.cli as cli
import factory.land as land_module
from factory.agents.fake import FakeRunner, FakeStep, maker_done
from factory.artifacts import read_header
from factory.cli import main
from factory.config import load_config
from factory.engine import LoopEngine
from factory.goal import load_goal
from factory.inbox import Inbox
from factory.state import RunStore
from factory.util import git


def _commit_on_main(root, name, content, message="cambio en main"):
    (root / name).write_text(content)
    git(root, "add", name)
    git(root, "commit", "-qm", message)


def _completed(tmp_path, criteria=None, edits=None):
    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(write_goal(root, criteria=criteria), config.loop)
    runner = FakeRunner(maker=[maker_done("hecho", **(edits or {"a.txt": "1\n"}))])
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    assert state.status == "completed"
    return root, config, state


def _land(root, run_id, *extra):
    return main(["--root", str(root), "land", run_id, *extra])


# ---------------------------------------------------------------- precondiciones (5.1)
def test_checkout_principal_con_cambios(tmp_path, capsys):
    root, _, state = _completed(tmp_path)
    before = git(root, "rev-parse", "main")
    (root / "prompts" / "maker.md").write_text("editado a mano\n")  # archivo versionado
    assert _land(root, state.run_id) == 1
    assert "cambios sin commitear" in capsys.readouterr().err
    assert git(root, "rev-parse", "main") == before


def test_archivos_sin_seguimiento_no_bloquean(tmp_path):
    root, _, state = _completed(tmp_path)
    (root / "notas-sueltas.txt").write_text("borrador\n")  # sin seguimiento
    assert _land(root, state.run_id) == 0


def test_ejecucion_no_completada(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(write_goal(root), config.loop)
    ask = FakeStep(output={"status": "needs_human", "summary": "?", "question": "¿?"})
    state = LoopEngine(config, goal, FakeRunner(maker=[ask]), echo=lambda _: None).run()
    assert _land(root, state.run_id) == 1
    assert f"factory goal rework {state.run_id}" in capsys.readouterr().err


def test_checkout_en_otra_rama_y_rama_inexistente(tmp_path, capsys):
    root, _, state = _completed(tmp_path)
    git(root, "switch", "-q", "-c", "otra")
    assert _land(root, state.run_id) == 1
    assert "no en 'main'" in capsys.readouterr().err
    git(root, "switch", "-q", "main")
    git(root, "branch", "-D", state.branch)
    assert _land(root, state.run_id) == 1
    assert "no existe" in capsys.readouterr().err


# ---------------------------------------------------------------- merge exacto (5.2)
def test_la_rama_principal_avanzo_y_el_merge_rompe_los_tests(tmp_path, capsys):
    criteria = (
        "  - name: a\n    run: test -f a.txt\n  - name: sin-roto\n    run: test ! -f roto.txt\n"
    )
    root, config, state = _completed(tmp_path, criteria=criteria)
    _commit_on_main(root, "roto.txt", "x\n")
    before = git(root, "rev-parse", "main")
    assert _land(root, state.run_id) == 1
    assert "criterio fallido: sin-roto" in capsys.readouterr().err
    assert git(root, "rev-parse", "main") == before
    checks = RunStore(config.state_path).run_dir(state.run_id) / "land" / "checks.md"
    assert read_header(checks)["GATE"] == "FAIL"
    assert not (config.worktrees_path / f"land-{state.run_id}").exists()


def test_conflicto_de_merge(tmp_path, capsys):
    criteria = "  - name: readme\n    run: test -f README.md\n"
    root, config, state = _completed(
        tmp_path, criteria=criteria, edits={"README.md": "versión de la rama\n"}
    )
    _commit_on_main(root, "README.md", "versión de main\n")
    before = git(root, "rev-parse", "main")
    assert _land(root, state.run_id) == 1
    err = capsys.readouterr().err
    assert "Conflicto" in err and "README.md" in err
    assert git(root, "rev-parse", "main") == before
    assert not (config.worktrees_path / f"land-{state.run_id}").exists()
    assert "land-" not in git(root, "worktree", "list")


# ---------------------------------------------------------------- avance de main (5.3)
def test_integracion_correcta(tmp_path, capsys):
    root, config, state = _completed(tmp_path)
    remote = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    main_before = git(root, "rev-parse", "main")
    branch_tip = git(root, "rev-parse", state.branch)
    assert _land(root, state.run_id) == 0
    head = git(root, "rev-parse", "main")
    assert git(root, "rev-list", "--parents", "-n", "1", head).split()[1:] == [
        main_before,
        branch_tip,
    ]
    assert (root / "a.txt").read_text() == "1\n"
    assert git(root, "ls-remote", "origin") == ""
    assert "sin push" in capsys.readouterr().out


def test_la_rama_principal_cambio_durante_la_verificacion(tmp_path, monkeypatch, capsys):
    root, config, state = _completed(tmp_path)
    original = land_module.run_criteria

    def concurrent(*args, **kwargs):
        result = original(*args, **kwargs)
        _commit_on_main(root, "concurrente.txt", "x\n", "commit concurrente")
        return result

    monkeypatch.setattr(land_module, "run_criteria", concurrent)
    assert _land(root, state.run_id) == 1
    assert "cambió durante la verificación" in capsys.readouterr().err
    assert git(root, "log", "-1", "--format=%s", "main") == "commit concurrente"


def test_bandeja_y_estado_tras_integrar(tmp_path, capsys):
    root, config, state = _completed(tmp_path)
    assert _land(root, state.run_id) == 0
    head = git(root, "rev-parse", "main")
    entry = next(e for e in Inbox(config.state_path).entries() if e.id == state.run_id)
    assert entry.status == "reviewed" and head[:10] in entry.resolution
    saved = RunStore(config.state_path).load(state.run_id)
    assert saved.landed_commit == head
    decision = RunStore(config.state_path).run_dir(state.run_id) / "decision.md"
    assert read_header(decision)["LANDED"] == head
    capsys.readouterr()
    assert _land(root, state.run_id) == 1
    assert "ya fue integrada" in capsys.readouterr().err


def test_comprobacion_previa(tmp_path, capsys):
    root, config, state = _completed(tmp_path)
    before = git(root, "rev-parse", "main")
    assert _land(root, state.run_id, "--dry-run") == 0
    assert "Integración posible" in capsys.readouterr().out
    assert git(root, "rev-parse", "main") == before
    assert Inbox(config.state_path).pending()[0].id == state.run_id


def test_borrar_rama_al_integrar(tmp_path, capsys):
    root, _, state = _completed(tmp_path)
    assert _land(root, state.run_id, "--delete-branch") == 0
    assert git(root, "branch", "--list", state.branch) == ""


# ---------------------------------------------------------------- solo por orden humana (5.4)
def test_ejecucion_completada_sin_integrar(tmp_path, monkeypatch):
    root = make_loop_repo(tmp_path)
    before = git(root, "rev-parse", "main")
    monkeypatch.setattr(
        cli, "make_runner", lambda _c: FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    )
    assert main(["--root", str(root), "goal", "run", str(write_goal(root))]) == 0
    monitor = write_goal(root, extra="mode: monitor\n")
    assert main(["--root", str(root), "tick", str(monitor)]) == 0
    assert git(root, "rev-parse", "main") == before
    src = Path(__file__).resolve().parents[1] / "src" / "factory"
    for module in ("engine.py", "tick.py"):
        assert "land" not in "".join(
            line
            for line in (src / module).read_text().splitlines()
            if line.startswith(("from", "import"))
        )
