"""Escenarios de `goal-loop` y `maker-checker-loop` sobre el motor de rondas (agente simulado)."""

from conftest import make_loop_repo, write_goal

from factory.agents.fake import FakeRunner, FakeStep, finding, maker_done, verdict
from factory.config import load_config
from factory.engine import LoopEngine
from factory.goal import load_goal
from factory.records import EventLog
from factory.state import RunStore
from factory.util import git


def run_loop(root, runner, **goal_kwargs):
    config = load_config(root)
    goal = load_goal(write_goal(root, **goal_kwargs), config.loop)
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    return config, state


def branch_files(root, state):
    return git(root, "ls-tree", "-r", "--name-only", state.branch).splitlines()


def test_segunda_ronda_tras_un_fallo_usa_sesion_nueva_con_feedback(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("creé a", **{"a.txt": "1"}), maker_done("creé b", **{"b.txt": "1"})],
    )
    _, state = run_loop(root, runner, files=("a.txt", "b.txt"))
    assert state.status == "completed" and len(state.rounds) == 2
    first, second = runner.calls_for("maker")
    assert first is not second and "Primera ronda." in first.prompt
    assert "Crear los archivos pedidos" in second.prompt
    assert "Ronda más reciente: Ronda 1" in second.prompt  # resumen acotado del estado
    assert "❌ b.txt" in second.prompt  # fallos concretos de la ronda 1
    assert "Primera ronda." not in second.prompt


def test_el_agente_declara_exito_pero_un_test_falla(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(maker=[maker_done("¡todo listo!")])
    _, state = run_loop(root, runner, max_rounds=2, no_progress=5)
    assert state.status == "max_rounds"
    assert all(not r.approved and r.criteria == {"a.txt": False} for r in state.rounds)


def test_modificacion_de_ruta_prohibida_se_revierte(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            maker_done("toqué algo prohibido", **{"a.txt": "1", "prohibido/x.txt": "no"}),
            maker_done("ahora bien", **{"a.txt": "1"}),
        ]
    )
    _, state = run_loop(root, runner)
    first = state.rounds[0]
    assert first.decision == "scope_revert" and "prohibido/x.txt" in first.note
    assert "prohibido/x.txt" in runner.calls_for("maker")[1].prompt
    assert "prohibido/x.txt" not in branch_files(root, state)
    assert state.status == "completed"


def test_feature_list_siempre_protegida(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(maker=[maker_done("x", **{"a.txt": "1", "feature_list.json": "{}"})])
    _, state = run_loop(root, runner, max_rounds=1)
    assert state.rounds[0].decision == "scope_revert"


def test_el_checker_intenta_modificar_archivos(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("a", **{"a.txt": "1"})],
        checker=[
            FakeStep(output={"verdict": "pass", "findings": []}, edits={"a.txt": "manipulado"}),
            verdict("pass"),
        ],
    )
    _, state = run_loop(root, runner)
    first = state.rounds[0]
    assert not first.approved and "el checker modificó archivos" in first.note
    assert first.checker_verdict == "inválido"
    assert git(root, "show", f"{state.branch}:a.txt") == "1"
    assert state.status == "completed" and state.rounds[1].approved


def test_entrada_del_checker_diff_acumulado_sin_conversacion_del_maker(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            maker_done("RAZONAMIENTO-SECRETO-1", **{"a.txt": "uno"}),
            maker_done("RAZONAMIENTO-SECRETO-2", **{"b.txt": "dos"}),
        ]
    )
    _, state = run_loop(root, runner, files=("a.txt", "b.txt"))
    second = runner.calls_for("checker")[1]
    assert "Diff acumulado desde el commit base" in second.prompt
    assert "+uno" in second.prompt and "+dos" in second.prompt
    assert "test -f a.txt" in second.prompt  # criterios
    assert "✅ a.txt" in second.prompt  # resultados de verificación
    assert "RAZONAMIENTO-SECRETO" not in second.prompt
    assert second.json_schema["required"] == ["verdict", "findings"]


def test_ronda_final_pequena_tras_rondas_previas(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            maker_done("debilité un test", **{"tests_debiles.py": "assert True  # debilitado\n"}),
            maker_done("fix mínimo", **{"a.txt": "1"}),
        ],
        checker=[
            verdict("fail", finding("medium")),
            verdict(
                "fail", finding("critical", "tests_debiles.py:1", description="test debilitado")
            ),
            verdict("pass"),
        ],
    )
    _, state = run_loop(root, runner, max_rounds=2)
    final_checker = runner.calls_for("checker")[1]
    assert "debilitado" in final_checker.prompt  # cambio de la ronda 1 en el diff acumulado
    assert not state.rounds[1].approved and state.status == "max_rounds"


def test_modelos_distintos_por_rol(tmp_path):
    root = make_loop_repo(tmp_path)
    (root / "factory.toml").write_text(
        '[roles.maker]\nmodel = "haiku"\n[roles.checker]\nmodel = "opus"\n'
    )
    runner = FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})])
    config, state = run_loop(root, runner)
    assert runner.calls_for("maker")[0].model == "haiku"
    assert runner.calls_for("checker")[0].model == "opus"
    events = EventLog(RunStore(config.state_path).run_dir(state.run_id)).read()
    models = {e["role"]: e["model"] for e in events if e["type"] == "agent"}
    assert models == {"maker": "haiku", "checker": "opus"}


def test_tests_pasan_pero_el_checker_rechaza(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("a", **{"a.txt": "1"})],
        checker=[
            verdict("fail", finding("critical", "a.txt:1", description="contenido inválido")),
            verdict("pass"),
        ],
    )
    _, state = run_loop(root, runner)
    first = state.rounds[0]
    assert first.criteria == {"a.txt": True} and not first.approved
    assert "contenido inválido" in runner.calls_for("maker")[1].prompt


def test_checker_aprueba_pero_un_test_falla(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(maker=[maker_done("nada")], checker=[verdict("pass")])
    _, state = run_loop(root, runner, max_rounds=1)
    assert state.rounds[0].checker_verdict == "pass" and not state.rounds[0].approved


def test_correccion_guiada(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("a", **{"a.txt": "1"})],
        checker=[
            verdict(
                "fail",
                finding(
                    "medium",
                    "src/mod.py:42",
                    evidence="devuelve None",
                    suggestion="lanzar ValueError",
                ),
            ),
            verdict("pass"),
        ],
    )
    run_loop(root, runner)
    second = runner.calls_for("maker")[1].prompt
    for text in ("[medium] src/mod.py:42", "devuelve None", "lanzar ValueError"):
        assert text in second


def test_ronda_que_empeora_vuelve_a_la_mejor(tmp_path):
    root = make_loop_repo(tmp_path)
    files = ("f1", "f2", "f3", "f4", "f5")
    runner = FakeRunner(
        maker=[
            maker_done("cuatro", f1="1", f2="1", f3="1", f4="1"),
            FakeStep(
                output={"status": "done", "summary": "rompí"},
                edits={"f1": None, "f2": None, "f3": None},
            ),
            maker_done("quinto", f5="1"),
        ]
    )
    _, state = run_loop(root, runner, files=files)
    r1, r2, r3 = state.rounds
    assert (r1.score, r1.decision) == (4, "keep")
    assert (r2.score, r2.decision) == (1, "revert") and "ratchet" in r2.note
    assert "se revirtió" in runner.calls_for("maker")[2].prompt
    assert r3.score == 5 and state.status == "completed"
    assert set(files) <= set(branch_files(root, state))


def test_ronda_que_mejora_o_iguala_se_conserva(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("uno", **{"a.txt": "1"}), maker_done("igual", **{"c.txt": "1"})],
        checker=[verdict("fail", finding()), verdict("fail", finding()), verdict("pass")],
    )
    _, state = run_loop(root, runner, files=("a.txt", "b.txt"), max_rounds=2)
    r1, r2 = state.rounds
    assert r1.decision == r2.decision == "keep"
    assert state.best_round == 2 and state.best_commit == r2.commit
    assert {"a.txt", "c.txt"} <= set(branch_files(root, state))
