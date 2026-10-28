"""Escenario de `maker-checker-loop`: promoción de la feature asociada por el orquestador."""

import json

import pytest
from conftest import make_feature, make_loop_repo, write_goal

from factory.agents.fake import FakeRunner, maker_done
from factory.config import load_config
from factory.engine import LoopEngine
from factory.features import FeatureError
from factory.goal import load_goal
from factory.util import git


def test_ejecucion_completada_con_feature_asociada(tmp_path):
    root = make_loop_repo(tmp_path, features=(make_feature("f-1", verification=["test -f a.txt"]),))
    config = load_config(root)
    goal = load_goal(write_goal(root, extra="feature: f-1\n"), config.loop)
    runner = FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    assert state.status == "completed"
    on_branch = json.loads(git(root, "show", f"{state.branch}:feature_list.json"))
    feature = on_branch["features"][0]
    assert feature["status"] == "passing"
    assert feature["evidence"][0]["command"] == "test -f a.txt"
    assert feature["evidence"][0]["run_id"] == state.run_id
    assert "promover feature f-1" in git(root, "log", "-1", "--format=%s", state.branch)
    on_main = json.loads((root / "feature_list.json").read_text())
    assert on_main["features"][0]["status"] == "not_started"  # main no cambia
    assert "promovida" in state.summary


def test_feature_inexistente_no_inicia_el_loop(tmp_path):
    root = make_loop_repo(tmp_path, features=(make_feature("f-1"),))
    config = load_config(root)
    goal = load_goal(write_goal(root, extra="feature: no-existe\n"), config.loop)
    runner = FakeRunner()
    with pytest.raises(FeatureError, match="no-existe"):
        LoopEngine(config, goal, runner, echo=lambda _: None).run()
    assert runner.calls == []
    assert not (config.state_path / "runs").exists()


def test_promocion_fallida_avisa_en_la_bandeja(tmp_path):
    from factory.inbox import Inbox

    root = make_loop_repo(tmp_path, features=(make_feature("f-1", verification=["test -f b.txt"]),))
    config = load_config(root)
    goal = load_goal(write_goal(root, extra="feature: f-1\n"), config.loop)
    runner = FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    assert state.status == "completed"
    assert "AVISO: la feature f-1 NO se promovió" in state.stop_reason
    on_branch = json.loads(git(root, "show", f"{state.branch}:feature_list.json"))
    assert on_branch["features"][0]["status"] == "not_started"
    [entry] = Inbox(config.state_path).pending()
    assert "NO se promovió" in entry.body and "NO se promovió" in entry.stop_reason
