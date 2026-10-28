"""Escenarios de `loop-state`: directorio de estado y archivo de estado del loop."""

import json
import shutil

from factory.records import EventLog
from factory.state import RoundRecord, RunState, RunStore, new_run_id


def _round(n, score=1, total=2, approved=False):
    criteria = {f"c{i}": i < score for i in range(total)}
    return RoundRecord(
        number=n,
        started="2026-10-27T10:00:00+00:00",
        maker_status="done",
        maker_summary=f"cambio {n}",
        changed_files=[f"src/f{n}.py"],
        criteria=criteria,
        score=score,
        checker_verdict="pass" if approved else "fail",
        findings=[]
        if approved
        else [{"severity": "medium", "location": "a:1", "description": "x"}],
        approved=approved,
        decision="keep",
        commit="abcdef1234567",
        cost_usd=0.1,
    )


def _store(tmp_path):
    return RunStore(tmp_path / "repo" / ".factory")


def test_run_id_unico_y_legible():
    a, b = new_run_id("demo"), new_run_id("demo")
    assert a != b and "-demo-" in a


def test_ejecucion_terminada_conserva_estado_tras_borrar_worktree(tmp_path):
    store = _store(tmp_path)
    worktree = tmp_path / "repo.factory-worktrees" / "r1"
    worktree.mkdir(parents=True)
    state = RunState(run_id="r1", goal_id="demo", objective="o", worktree=str(worktree))
    store.create(state, "---\nid: demo\n---\n")
    EventLog(store.run_dir("r1")).write("agent", round=1)
    state.status = "completed"
    store.save(state)
    shutil.rmtree(worktree)
    directory = store.run_dir("r1")
    assert {"state.json", "loop-state.md", "goal.md", "events.jsonl"} <= {
        p.name for p in directory.iterdir()
    }
    assert store.load("r1").status == "completed"


def test_estado_tras_una_ronda(tmp_path):
    store = _store(tmp_path)
    state = RunState(run_id="r2", goal_id="demo", objective="Subir cobertura")
    store.create(state, "g")
    for n in (1, 2, 3):
        state.rounds.append(_round(n, score=n % 3, total=2, approved=n == 3))
        store.save(state, max_rounds=8)
    text = (store.run_dir("r2") / "loop-state.md").read_text()
    for n in (1, 2, 3):
        assert f"### Ronda {n}" in text
    assert "**Ronda actual**: 3 / 8" in text
    assert "| Rondas completadas | 3 |" in text
    assert "| Rondas aprobadas | 1 |" in text
    assert "| Rondas fallidas | 2 |" in text
    assert "| Archivos cambiados | 3 |" in text
    assert json.loads((store.run_dir("r2") / "state.json").read_text())["rounds"][2]["number"] == 3


def test_interrupcion_deja_estado_legible(tmp_path):
    store = _store(tmp_path)
    state = RunState(run_id="r3", goal_id="demo", objective="o")
    store.create(state, "g")
    state.rounds.append(_round(1))
    store.save(state)
    # La ronda 2 estaba a medias: no se añadió. Se marca la interrupción.
    state.status = "interrupted"
    state.stop_reason = "interrumpido por el usuario (SIGINT)"
    store.save(state)
    text = (store.run_dir("r3") / "loop-state.md").read_text()
    assert "**Estado actual**: interrupted" in text
    assert "### Ronda 1" in text and "### Ronda 2" not in text
    assert store.load("r3").status == "interrupted"
    assert not list(store.run_dir("r3").glob(".state.json*"))  # sin temporales a medias


def test_list_runs_ordena_por_inicio(tmp_path):
    store = _store(tmp_path)
    for run_id, started in (("a", "2026-01-01T00:00:00+00:00"), ("b", "2026-02-01T00:00:00+00:00")):
        store.create(RunState(run_id=run_id, goal_id="g", objective="o", started=started), "g")
    assert [s.run_id for s in store.list_runs()] == ["b", "a"]
