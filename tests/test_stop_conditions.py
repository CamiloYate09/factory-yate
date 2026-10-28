"""Escenarios de `goal-loop`/`maker-checker-loop`: condiciones de parada y códigos de salida."""

import subprocess

import pytest
from conftest import make_loop_repo, write_goal

from factory.agents.claude_code import ClaudeCodeRunner, build_argv
from factory.agents.fake import FakeRunner, FakeStep, maker_done
from factory.config import load_config
from factory.engine import LoopEngine, exit_code
from factory.goal import load_goal
from factory.inbox import Inbox
from factory.records import EventLog
from factory.state import RunStore
from factory.util import git


def run_loop(root, runner, **goal_kwargs):
    config = load_config(root)
    goal = load_goal(write_goal(root, **goal_kwargs), config.loop)
    return config, LoopEngine(config, goal, runner, echo=lambda _: None).run()


def test_exito(tmp_path):
    root = make_loop_repo(tmp_path)
    config, state = run_loop(root, FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})]))
    assert state.status == "completed" and exit_code(state) == 0
    assert state.finished and "aprobados" in state.stop_reason
    assert not (config.worktrees_path / state.run_id).exists()  # worktree eliminado
    assert git(root, "branch", "--list", state.branch)  # rama conservada


def test_sin_progreso(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(maker=[maker_done("lo intento")])
    _, state = run_loop(root, runner, max_rounds=8, no_progress=3)
    assert state.status == "stalled" and exit_code(state) == 3
    assert len(state.rounds) == 3
    signature = state.rounds[0].signature
    assert signature and all(r.signature == signature for r in state.rounds)
    assert any(signature in b for b in state.blockers)


def test_presupuesto_agotado_no_inicia_ronda_nueva(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(maker=[FakeStep(output={"status": "done", "summary": "x"}, cost_usd=0.6)])
    _, state = run_loop(root, runner, budget=1.0, max_rounds=8, no_progress=8)
    assert state.status == "budget_exhausted" and exit_code(state) == 5
    assert len(state.rounds) == 2  # 0.61 tras la ronda 1; 1.22 tras la 2 → no hay ronda 3
    assert state.total_cost_usd >= 1.0
    assert len(runner.calls_for("maker")) == 2


def test_bloqueo_humano(tmp_path):
    root = make_loop_repo(tmp_path)
    ask = FakeStep(
        output={"status": "needs_human", "summary": "duda", "question": "¿Uso SQLite o Postgres?"}
    )
    config, state = run_loop(root, FakeRunner(maker=[ask]))
    assert state.status == "blocked" and exit_code(state) == 6
    assert state.rounds[0].human_needed
    [entry] = Inbox(config.state_path).pending()
    assert entry.question == "¿Uso SQLite o Postgres?" and entry.result == "blocked"


def test_cli_del_agente_no_disponible(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = ClaudeCodeRunner(str(tmp_path / "no-existe-claude"))
    _, state = run_loop(root, runner)
    assert state.status == "agent_error" and exit_code(state) == 7
    assert len(state.rounds) == 2  # agent_error_rounds = 2
    assert "No se encontró el ejecutable" in state.stop_reason
    assert "claude --version" in state.stop_reason


def test_error_aislado_no_detiene_el_loop(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(maker=[FakeStep(timeout=True), maker_done("a", **{"a.txt": "1"})])
    _, state = run_loop(root, runner)
    assert state.rounds[0].decision == "error" and "tiempo agotado" in state.rounds[0].note
    assert state.status == "completed"


def test_el_maker_intenta_hacer_push(tmp_path):
    root = make_loop_repo(tmp_path)
    # Ni siquiera un goal.md que vacía denied_tools quita la denegación de publicar.
    extra = "roles:\n  maker: {denied_tools: []}\n"
    remote = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    denial = {"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD"}}
    runner = FakeRunner(
        maker=[
            FakeStep(
                output={"status": "done", "summary": "intenté publicar"},
                edits={"a.txt": "1"},
                permission_denials=[denial],
            )
        ]
    )
    config, state = run_loop(root, runner, extra=extra)
    maker_request = runner.calls_for("maker")[0]
    argv = build_argv(maker_request)  # lo que recibiría el CLI real con esta petición
    disallowed = argv[argv.index("--disallowedTools") + 1].split(",")
    assert "Bash(git push:*)" in disallowed and "Bash(gh:*)" in disallowed
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert not any("dangerously" in a or "bypass" in a for a in argv)
    events = EventLog(RunStore(config.state_path).run_dir(state.run_id)).read()
    assert denial in next(e for e in events if e.get("role") == "maker")["permission_denials"]
    assert git(root, "ls-remote", "origin") == ""  # ningún remoto recibió cambios


def test_interrupcion(tmp_path):
    root = make_loop_repo(tmp_path)

    def interrupt(_request):
        raise KeyboardInterrupt

    runner = FakeRunner(maker=[maker_done("a", **{"a.txt": "1"}), FakeStep(action=interrupt)])
    config, state = run_loop(root, runner, files=("a.txt", "b.txt"))
    assert state.status == "interrupted" and exit_code(state) == 130
    assert len(state.rounds) == 1
    saved = RunStore(config.state_path).load(state.run_id)
    assert saved.status == "interrupted"
    assert Inbox(config.state_path).pending()[0].result == "interrupted"


def test_max_rounds(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("x", **{"a.txt": "1"})],
        checker=[FakeStep(output={"verdict": "fail", "findings": []})],
    )
    _, state = run_loop(root, runner, max_rounds=2)
    assert state.status == "max_rounds" and exit_code(state) == 4
    assert all(r.checker_verdict == "fail" for r in state.rounds)


def test_error_interno_queda_registrado(tmp_path, monkeypatch):
    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(write_goal(root), config.loop)
    engine = LoopEngine(config, goal, FakeRunner(), echo=lambda _: None)

    def boom(*_args, **_kwargs):
        raise RuntimeError("fallo de disco")

    monkeypatch.setattr(engine, "_round", boom)
    with pytest.raises(RuntimeError):
        engine.run()
    [state] = RunStore(config.state_path).list_runs()
    assert state.status == "interrupted" and "fallo de disco" in state.stop_reason


def test_sin_presupuesto_tras_el_maker_no_se_invoca_al_checker(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            FakeStep(output={"status": "done", "summary": "x"}, edits={"a.txt": "1"}, cost_usd=1.0)
        ]
    )
    _, state = run_loop(root, runner, budget=1.0)
    assert runner.calls_for("checker") == []
    assert state.rounds[0].checker_verdict == "omitido" and not state.rounds[0].approved
    assert state.status == "budget_exhausted" and state.total_cost_usd == 1.0


def test_fallo_al_crear_el_worktree_no_deja_la_ejecucion_en_running(tmp_path, monkeypatch):
    import factory.engine as engine_module
    from factory.util import GitError

    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(write_goal(root), config.loop)

    def fail(*_args, **_kwargs):
        raise GitError("la rama ya existe")

    monkeypatch.setattr(engine_module, "create_worktree", fail)
    with pytest.raises(GitError):
        LoopEngine(config, goal, FakeRunner(), echo=lambda _: None).run()
    [state] = RunStore(config.state_path).list_runs()
    assert state.status == "interrupted" and "la rama ya existe" in state.stop_reason
    assert Inbox(config.state_path).pending()[0].result == "interrupted"
