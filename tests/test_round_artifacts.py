"""Escenarios de `loop-state`: artefactos legibles por ronda escritos por el motor."""

import subprocess

from conftest import make_loop_repo, write_goal

from factory.agents.fake import FakeRunner, FakeStep, maker_done
from factory.artifacts import read_header
from factory.config import load_config
from factory.engine import LoopEngine
from factory.goal import load_goal
from factory.state import RunStore


def _run(root, runner, **kwargs):
    config = load_config(root)
    goal = load_goal(write_goal(root, **kwargs), config.loop)
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    return state, RunStore(config.state_path).run_dir(state.run_id)


def test_ronda_con_un_criterio_fallido(tmp_path):
    root = make_loop_repo(tmp_path)
    criteria = (
        "  - name: a\n    run: test -f a.txt\n"
        "  - name: b\n    run: test -f b.txt || (echo 'falta b.txt'; exit 1)\n"
    )
    runner = FakeRunner(maker=[maker_done("solo a", **{"a.txt": "1"})])
    state, run_dir = _run(root, runner, criteria=criteria, max_rounds=1)
    checks = run_dir / "rounds" / "1" / "checks.md"
    head = read_header(checks)
    assert head["GATE"] == "FAIL" and head["COMMIT"] == state.rounds[0].commit
    assert head["SCORE"] == "1/2"
    text = checks.read_text()
    assert "❌ b:" in text and "falta b.txt" in text
    for name in ("maker.md", "review.md"):
        assert (run_dir / "rounds" / "1" / name).exists()
    assert read_header(run_dir / "rounds" / "1" / "maker.md")["STATUS"] == "done"


def test_ronda_revertida_por_rutas_protegidas(tmp_path):
    root = make_loop_repo(tmp_path)
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("assert 1 == 1\n")
    (root / "factory.toml").write_text('[loop]\nprotected_paths = ["tests/**"]\n')
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "t"], cwd=root, check=True)
    runner = FakeRunner(
        maker=[maker_done("x", **{"a.txt": "1", "tests/test_a.py": "assert True\n"})]
    )
    _, run_dir = _run(root, runner, max_rounds=1)
    checks = run_dir / "rounds" / "1" / "checks.md"
    head = read_header(checks)
    assert head["GATE"] == "FAIL" and head["DECISION"] == "protected_revert"
    assert "tests/test_a.py (modificado)" in checks.read_text()
    assert read_header(run_dir / "rounds" / "1" / "review.md")["VERDICT"] == "no_invocado"


def test_decision_final(tmp_path):
    root = make_loop_repo(tmp_path)
    state, run_dir = _run(root, FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})]))
    head = read_header(run_dir / "decision.md")
    assert head["RESULT"] == "completed" and head["REASON"] == state.stop_reason
    assert head["BRANCH"] == state.branch and head["BEST_ROUND"] == "1"


def test_ronda_que_empeora(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            maker_done("dos", f1="1", f2="1"),
            FakeStep(output={"status": "done", "summary": "rompo"}, edits={"f1": None}),
            maker_done("tres", f3="1"),
        ]
    )
    state, run_dir = _run(root, runner, files=("f1", "f2", "f3"))
    r1, r2 = state.rounds[0], state.rounds[1]
    head = read_header(run_dir / "rounds" / "2" / "checks.md")
    assert head["COMMIT"] == r2.commit and head["REVERTED_TO"] == r1.commit
    assert head["DECISION"] == "revert"


def test_ronda_con_error_del_agente_tambien_deja_artefactos(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(maker=[FakeStep(error="boom"), maker_done("a", **{"a.txt": "1"})])
    _, run_dir = _run(root, runner)
    head = read_header(run_dir / "rounds" / "1" / "checks.md")
    assert head["GATE"] == "NOT_RUN" and head["DECISION"] == "error"
