"""Escenarios de `daily-brain`: notas diarias, alta manual, reindexado, protección y commit."""

import json

from factory.brain.daily import DailyBrain
from factory.cli import main


def _catalog(directory):
    return [json.loads(line) for line in (directory / "_catalog.jsonl").read_text().splitlines()]


def test_primera_nota(tmp_path):
    brain = DailyBrain(tmp_path / "brain-diario")
    path = brain.add(
        "Los worktrees deben vivir fuera del repo. Así no cargan el CLAUDE.md padre.",
        day="2026-10-28",
    )
    assert path.relative_to(brain.dir).as_posix().startswith("2026/10/2026-10-28-")
    [entry] = _catalog(brain.dir)
    assert entry["path"] == path.relative_to(brain.dir).as_posix()
    assert entry["title"].startswith("Los worktrees deben vivir fuera del repo")
    assert entry["keywords"] and entry["abstract"] == "Los worktrees deben vivir fuera del repo."
    assert entry["tokens"] > 0 and entry["source"] == "manual"
    assert "_catalog.jsonl" in (brain.dir / "AGENTS.md").read_text()
    assert entry["path"] in (brain.dir / "llms.txt").read_text()


def test_aprendizaje_manual(tmp_path, capsys):
    text = "En macOS no existe timeout; usar el de la herramienta"
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "brain",
                "learn",
                text,
                "--kind",
                "gotcha",
                "--tags",
                "macos,shell",
            ]
        )
        == 0
    )
    assert "factory brain commit" in capsys.readouterr().out
    [entry] = _catalog(tmp_path / "brain-diario")
    assert entry["type"] == "gotcha" and entry["tags"] == ["macos", "shell"]
    assert entry["source"] == "manual"
    note = (tmp_path / "brain-diario" / entry["path"]).read_text()
    assert "type: gotcha" in note and text in note


def test_nota_editada_a_mano(tmp_path, capsys):
    brain = DailyBrain(tmp_path / "brain-diario")
    path = brain.add("Primera versión del título", day="2026-10-28")
    path.write_text(
        path.read_text().replace("title: Primera versión del título", "title: Título corregido")
    )
    assert main(["--root", str(tmp_path), "brain", "reindex"]) == 0
    assert _catalog(brain.dir)[0]["title"] == "Título corregido"


def test_nota_con_frontmatter_roto(tmp_path, capsys):
    brain = DailyBrain(tmp_path / "brain-diario")
    brain.add("Nota válida", day="2026-10-28")
    broken = brain.dir / "2026" / "10" / "2026-10-28-rota.md"
    broken.write_text("---\ntitle: [sin cerrar\n---\ncuerpo\n")
    assert main(["--root", str(tmp_path), "brain", "reindex"]) == 1
    out = capsys.readouterr().out
    assert "2026/10/2026-10-28-rota.md" in out
    assert [e["title"] for e in _catalog(brain.dir)] == ["Nota válida"]


def test_titulos_repetidos_no_se_pisan(tmp_path):
    brain = DailyBrain(tmp_path / "brain-diario")
    a = brain.add("Mismo título", day="2026-10-28")
    b = brain.add("Mismo título", day="2026-10-28")
    assert a != b and len(_catalog(brain.dir)) == 2


def test_tipo_invalido(tmp_path):
    import pytest

    from factory.brain import BrainError

    with pytest.raises(SystemExit):  # argparse rechaza el tipo en el CLI
        main(["--root", str(tmp_path), "brain", "learn", "x", "--kind", "rumor"])
    with pytest.raises(BrainError, match="inválido"):
        DailyBrain(tmp_path / "brain-diario").add("x", kind="rumor")


def test_el_maker_escribe_en_el_cerebro_diario(tmp_path):
    from conftest import make_loop_repo, write_goal

    from factory.agents.fake import FakeRunner, maker_done
    from factory.config import load_config
    from factory.engine import LoopEngine
    from factory.goal import load_goal

    root = make_loop_repo(tmp_path)
    config = load_config(root)
    goal = load_goal(write_goal(root), config.loop)
    runner = FakeRunner(
        maker=[
            maker_done("anoto", **{"a.txt": "1", "brain-diario/2026/10/2026-10-28-x.md": "x"}),
            maker_done("bien", **{"a.txt": "1"}),
        ]
    )
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    first = state.rounds[0]
    assert first.decision == "scope_revert" and "brain-diario/2026/10/2026-10-28-x.md" in first.note
    assert "brain-diario/2026/10/2026-10-28-x.md" in runner.calls_for("maker")[1].prompt
    assert "brain-diario/**" in runner.calls_for("maker")[0].prompt  # visible en el alcance
    assert state.status == "completed"


def _repo_with_daily(tmp_path):
    from conftest import init_git_repo

    root = init_git_repo(tmp_path / "repo")
    (root / "app.py").write_text("x = 1\n")
    from factory.util import git

    git(root, "add", "-A")
    git(root, "commit", "-qm", "app")
    return root


def test_commit_con_otros_cambios_en_el_checkout(tmp_path, capsys):
    from factory.util import git

    root = _repo_with_daily(tmp_path)
    assert main(["--root", str(root), "brain", "learn", "Aprendí algo útil"]) == 0
    (root / "app.py").write_text("x = 2\n")  # cambio de código sin commitear
    assert main(["--root", str(root), "brain", "commit", "-m", "notas"]) == 0
    assert "solo con el cerebro diario" in capsys.readouterr().out
    files = git(root, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert files and all(f.startswith("brain-diario/") for f in files)
    assert git(root, "status", "--porcelain") == "M app.py"
    assert main(["--root", str(root), "brain", "commit"]) == 0
    assert "no tiene cambios" in capsys.readouterr().out


def test_aviso_de_cambios_pendientes(tmp_path, capsys):
    root = _repo_with_daily(tmp_path)
    assert main(["--root", str(root), "status"]) == 0
    assert "Cerebro diario con" not in capsys.readouterr().out
    main(["--root", str(root), "brain", "learn", "Otra nota"])
    capsys.readouterr()
    assert main(["--root", str(root), "status"]) == 0
    out = capsys.readouterr().out
    assert "[AVISO] Cerebro diario con" in out and "factory brain commit" in out


def test_land_sugiere_brain_commit(tmp_path, capsys):
    from conftest import make_loop_repo, write_goal

    from factory.agents.fake import FakeRunner, maker_done
    from factory.config import load_config
    from factory.engine import LoopEngine
    from factory.goal import load_goal
    from factory.util import git

    root = make_loop_repo(tmp_path)
    DailyBrain(root / "brain-diario").add("nota versionada", day="2026-10-28")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "diario")
    config = load_config(root)
    goal = load_goal(write_goal(root), config.loop)
    state = LoopEngine(
        config, goal, FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})]), echo=lambda _: None
    ).run()
    DailyBrain(root / "brain-diario").add("nota nueva sin commitear", day="2026-10-28")
    capsys.readouterr()
    assert main(["--root", str(root), "land", state.run_id]) == 1
    assert "factory brain commit" in capsys.readouterr().err
