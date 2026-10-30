"""Escenarios de `goal-loop`: rutas protegidas (detección y motor)."""

import subprocess

from conftest import make_loop_repo, write_goal

from factory.agents.fake import FakeRunner, FakeStep, maker_done
from factory.cli import main
from factory.config import load_config
from factory.engine import LoopEngine
from factory.gitops import create_worktree, preflight
from factory.goal import load_goal
from factory.protection import Protection, violations
from factory.util import git


def _wt(git_repo):
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "test_a.py").write_text("assert 1 == 1\n")
    (git_repo / "tests" / "test_b.py").write_text("assert 2 == 2\n")
    git(git_repo, "add", "-A")
    git(git_repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "tests")
    base = preflight(git_repo, "main")
    return create_worktree(git_repo, load_config(git_repo).worktrees_path, "r", base), base


PROT = Protection(critical=["factory.toml"], protected=["tests/**"])


def test_detecta_modificar_borrar_y_renombrar_pero_no_anadir(git_repo):
    wt, base = _wt(git_repo)
    (wt.path / "tests" / "test_a.py").write_text("assert True  # debilitado\n")
    (wt.path / "tests" / "test_b.py").rename(wt.path / "tests" / "test_b_renombrado.py")
    (wt.path / "tests" / "test_nuevo.py").write_text("assert 3 == 3\n")
    wt.snapshot("ronda")
    entries = wt.name_status(base)
    found = {(v.path, v.change) for v in violations(entries, PROT)}
    assert found == {("tests/test_a.py", "modificado"), ("tests/test_b.py", "renombrado")}


def test_borrado_de_archivo_protegido(git_repo):
    wt, base = _wt(git_repo)
    (wt.path / "tests" / "test_a.py").unlink()
    wt.snapshot("ronda")
    assert [str(v) for v in violations(wt.name_status(base), PROT)] == ["tests/test_a.py (borrado)"]


def test_archivo_creado_y_luego_modificado_no_es_violacion(git_repo):
    wt, base = _wt(git_repo)
    (wt.path / "tests" / "test_nuevo.py").write_text("x = 1\n")
    wt.snapshot("ronda 1")
    (wt.path / "tests" / "test_nuevo.py").write_text("x = 2\n")
    wt.snapshot("ronda 2")
    assert violations(wt.name_status(base), PROT) == []


def test_liberadas_y_criticas():
    prot = Protection(critical=["factory.toml"], protected=["tests/**"], released=["tests/a.py"])
    assert not prot.is_protected("tests/a.py") and prot.is_protected("tests/b.py")
    assert prot.is_protected("factory.toml")


# ---------------------------------------------------------------- escenarios con el motor


def _protected_repo(tmp_path, toml='[loop]\nprotected_paths = ["tests/**"]\n'):
    root = make_loop_repo(tmp_path)
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("assert 1 == 1\n")
    (root / "tests" / "test_b.py").write_text("assert 2 == 2\n")
    (root / "scripts").mkdir()
    check = root / "scripts" / "check.sh"
    check.write_text("#!/usr/bin/env bash\nexit 0\n")
    check.chmod(0o755)
    (root / "factory.toml").write_text(toml)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "tests"], cwd=root, check=True)
    return root


def _run(root, runner, extra="", files=("a.txt",), max_rounds=3):
    config = load_config(root)
    goal = load_goal(write_goal(root, files=files, extra=extra, max_rounds=max_rounds), config.loop)
    return LoopEngine(config, goal, runner, echo=lambda _: None).run()


def test_el_maker_modifica_un_test_existente_protegido(tmp_path):
    root = _protected_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            maker_done("debilito", **{"a.txt": "1", "tests/test_a.py": "assert True\n"}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    state = _run(root, runner)
    first = state.rounds[0]
    assert first.decision == "protected_revert"
    assert first.protected_violations == ["tests/test_a.py (modificado)"]
    assert "tests/test_a.py (modificado)" in runner.calls_for("maker")[1].prompt
    assert git(root, "show", f"{state.branch}:tests/test_a.py") == "assert 1 == 1"
    assert state.status == "completed"


def test_el_maker_anade_un_test_nuevo(tmp_path):
    root = _protected_repo(tmp_path)
    runner = FakeRunner(maker=[maker_done("nuevo", **{"a.txt": "1", "tests/test_c.py": "x = 1\n"})])
    state = _run(root, runner)
    assert state.rounds[0].decision == "keep" and state.status == "completed"
    assert "tests/test_c.py" in git(root, "ls-tree", "-r", "--name-only", state.branch)


def test_renombrar_un_archivo_protegido(tmp_path):
    root = _protected_repo(tmp_path)

    def rename(request):
        (request.cwd / "tests" / "test_b.py").rename(request.cwd / "tests" / "test_b2.py")

    runner = FakeRunner(
        maker=[
            FakeStep(output={"status": "done", "summary": "renombro"}, action=rename),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    state = _run(root, runner)
    assert state.rounds[0].protected_violations == ["tests/test_b.py (renombrado)"]


def test_el_maker_edita_el_script_de_verificacion(tmp_path):
    root = _protected_repo(tmp_path, toml="")
    criteria = "  - name: check\n    run: ./scripts/check.sh\n  - name: a\n    run: test -f a.txt\n"
    runner = FakeRunner(
        maker=[
            maker_done("trampa", **{"a.txt": "1", "scripts/check.sh": "#!/bin/sh\nexit 0 # x\n"}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    config = load_config(root)
    goal = load_goal(write_goal(root, criteria=criteria), config.loop)
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    assert state.rounds[0].protected_violations == ["scripts/check.sh (modificado)"]


def test_objetivo_que_debe_actualizar_un_test_existente(tmp_path):
    root = _protected_repo(tmp_path)
    text_goal = write_goal(root)
    content = text_goal.read_text().replace(
        'scope:\n  allow: ["**"]\n',
        'scope:\n  allow: ["**"]\n  allow_modify: ["tests/test_a.py"]\n',
    )
    text_goal.write_text(content)  # el objetivo libera solo tests/test_a.py
    runner = FakeRunner(
        maker=[
            maker_done("actualizo a", **{"a.txt": "1", "tests/test_a.py": "assert 10 == 10\n"}),
        ]
    )
    config = load_config(root)
    state = LoopEngine(config, load_goal(text_goal, config.loop), runner, echo=lambda _: None).run()
    assert state.rounds[0].decision == "keep" and state.status == "completed"
    runner_b = FakeRunner(
        maker=[maker_done("toco b", **{"a.txt": "1", "tests/test_b.py": "assert 0 == 0\n"})]
    )
    state_b = LoopEngine(
        config, load_goal(text_goal, config.loop), runner_b, echo=lambda _: None
    ).run()
    assert state_b.rounds[0].protected_violations == ["tests/test_b.py (modificado)"]


def test_simulacion_muestra_la_proteccion_efectiva(tmp_path, capsys):
    root = _protected_repo(tmp_path)
    goal = write_goal(root)
    goal.write_text(
        goal.read_text().replace(
            'scope:\n  allow: ["**"]\n',
            'scope:\n  allow: ["**"]\n  allow_modify: ["tests/test_a.py"]\n',
        )
    )
    assert main(["--root", str(root), "goal", "run", str(goal), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert (
        "Rutas protegidas (críticas, siempre): feature_list.json, factory.toml, prompts/**" in out
    )
    assert "Rutas protegidas (configuración/objetivo): tests/**" in out
    assert "Liberadas por el objetivo: tests/test_a.py" in out


# ------------------------------------------------- definiciones del equipo (add-equipo-ideal)


def _team_repo(tmp_path):
    """Repo de loop con un agente y una skill del equipo ya versionados y sin `protected_paths`:
    lo que se protege es solo por ser crítico."""
    root = _protected_repo(tmp_path, toml="")
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "agents" / "qa.md").write_text("---\nname: qa\n---\nRevisor.\n")
    (root / ".claude" / "skills" / "equipo").mkdir(parents=True)
    (root / ".claude" / "skills" / "equipo" / "SKILL.md").write_text("# Reglamento\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "equipo"], cwd=root, check=True)
    return root


def test_el_maker_edita_un_agente_del_equipo(tmp_path):
    root = _team_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            maker_done("aflojo qa", **{"a.txt": "1", ".claude/agents/qa.md": "Aprueba todo.\n"}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    state = _run(root, runner)
    first = state.rounds[0]
    assert first.decision == "protected_revert"
    assert first.protected_violations == [".claude/agents/qa.md (modificado)"]
    assert ".claude/agents/qa.md (modificado)" in runner.calls_for("maker")[1].prompt
    assert git(root, "show", f"{state.branch}:.claude/agents/qa.md").endswith("Revisor.")
    assert state.status == "completed"


def test_comodin_que_solapa_en_parte_con_un_critico(tmp_path):
    root = _team_repo(tmp_path)
    text_goal = write_goal(root)
    text_goal.write_text(
        text_goal.read_text().replace(
            'scope:\n  allow: ["**"]\n',
            'scope:\n  allow: ["**"]\n  allow_modify: [".claude/*/qa.md"]\n',
        )
    )  # la validación lo acepta (heurística), pero no libera el crítico
    runner = FakeRunner(
        maker=[
            maker_done("aflojo qa", **{"a.txt": "1", ".claude/agents/qa.md": "Aprueba todo.\n"}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    config = load_config(root)
    goal = load_goal(text_goal, config.loop)
    assert goal.allow_modify == [".claude/*/qa.md"]
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    assert state.rounds[0].decision == "protected_revert"
    assert state.rounds[0].protected_violations == [".claude/agents/qa.md (modificado)"]
    assert git(root, "show", f"{state.branch}:.claude/agents/qa.md").endswith("Revisor.")


def test_el_maker_borra_una_skill_del_equipo(tmp_path):
    root = _team_repo(tmp_path)
    runner = FakeRunner(
        maker=[
            maker_done("borro", **{"a.txt": "1", ".claude/skills/equipo/SKILL.md": None}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    state = _run(root, runner)
    assert state.rounds[0].decision == "protected_revert"
    assert state.rounds[0].protected_violations == [".claude/skills/equipo/SKILL.md (borrado)"]
    assert git(root, "show", f"{state.branch}:.claude/skills/equipo/SKILL.md") == "# Reglamento"
    assert state.status == "completed"


def test_el_maker_crea_un_agente_nuevo_del_equipo(tmp_path):
    root = _team_repo(tmp_path)
    new_files = {".claude/agents/nuevo.md": "nuevo\n", ".claude/skills/nueva/SKILL.md": "# x\n"}
    runner = FakeRunner(maker=[maker_done("ficho", **{"a.txt": "1", **new_files})])
    state = _run(root, runner)
    assert state.rounds[0].decision == "keep" and state.status == "completed"
    tracked = git(root, "ls-tree", "-r", "--name-only", state.branch).splitlines()
    assert set(new_files) <= set(tracked)


# ------------------------------------------------------------------ rutas con caracteres no ASCII


def test_un_critico_con_tildes_sigue_protegido(tmp_path):
    root = _team_repo(tmp_path)
    (root / ".claude" / "agents" / "métricas.md").write_text("---\nname: métricas\n---\nX.\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "tildes"], cwd=root, check=True)
    runner = FakeRunner(
        maker=[
            maker_done("toco", **{"a.txt": "1", ".claude/agents/métricas.md": "Otro.\n"}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    state = _run(root, runner)
    assert state.rounds[0].decision == "protected_revert"
    assert state.rounds[0].protected_violations == [".claude/agents/métricas.md (modificado)"]


def test_name_status_y_changed_files_sin_comillas(tmp_path):
    root = _protected_repo(tmp_path, toml="")
    wt = create_worktree(root, tmp_path / "wts", "r1", "main")
    (wt.path / "tests" / "test_a.py").rename(wt.path / "tests" / "test_ñandú.py")
    (wt.path / "docs").mkdir()
    (wt.path / "docs" / "guía.md").write_text("x\n")
    assert wt.changed_files("HEAD") == ["docs/guía.md", "tests/test_a.py", "tests/test_ñandú.py"]
    base = wt.head()
    wt.snapshot("renombro")
    [(status, old, new)] = [e for e in wt.name_status(base) if e[0].startswith("R")]
    assert (old, new) == ("tests/test_a.py", "tests/test_ñandú.py")
    assert ("A", "docs/guía.md", None) in wt.name_status(base)


def test_changed_files_conserva_el_espacio_inicial(tmp_path):
    root = _protected_repo(tmp_path, toml="")
    wt = create_worktree(root, tmp_path / "wts", "r1", "main")
    (wt.path / " empieza.txt").write_text("x\n")
    assert wt.changed_files("HEAD") == [" empieza.txt"]


def test_fuera_de_alcance_con_tildes_se_revierte(tmp_path):
    root = _protected_repo(tmp_path, toml="")
    runner = FakeRunner(
        maker=[
            maker_done("fuera", **{"a.txt": "1", "prohibido/guía.md": "x\n"}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    state = _run(root, runner)  # GOAL_TEMPLATE: deny ["prohibido/**"]
    assert state.rounds[0].decision == "scope_revert"
    assert "prohibido/guía.md" in runner.calls_for("maker")[1].prompt
