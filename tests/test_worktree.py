"""Escenarios de `maker-checker-loop`: aislamiento por worktree fuera del repo."""

import pytest
from conftest import init_git_repo

from factory.config import load_config
from factory.gitops import (
    PreflightError,
    create_worktree,
    diffstat,
    orphan_worktrees,
    preflight,
    remove_worktree,
)
from factory.util import git


def test_repositorio_sin_commits(tmp_path):
    repo = init_git_repo(tmp_path / "repo", commit=False)
    with pytest.raises(PreflightError, match="commit inicial"):
        preflight(repo, "main")


def test_directorio_no_git(tmp_path):
    with pytest.raises(PreflightError, match="no es un repositorio git"):
        preflight(tmp_path, "main")


def test_worktree_fuera_del_repo(git_repo):
    config = load_config(git_repo)
    base = preflight(git_repo, "main")
    wt = create_worktree(git_repo, config.worktrees_path, "run-1", base)
    assert wt.path.exists() and wt.branch == "factory/run-1"
    assert git_repo.resolve() not in wt.path.resolve().parents
    assert wt.path.resolve().parent == (git_repo.parent / "repo.factory-worktrees").resolve()


def test_ejecucion_concurrente_con_trabajo_humano(git_repo):
    config = load_config(git_repo)
    base = preflight(git_repo, "main")
    wt = create_worktree(git_repo, config.worktrees_path, "run-2", base)
    (git_repo / "humano.txt").write_text("trabajo del humano\n")
    (wt.path / "README.md").write_text("cambio del loop\n")
    (wt.path / "nuevo.py").write_text("x = 1\n")
    assert wt.changed_files(base) == ["README.md", "nuevo.py"]
    commit = wt.snapshot("factory(run-2): ronda 1")
    assert commit and commit != base
    assert (git_repo / "README.md").read_text() == "demo\n"
    assert (git_repo / "humano.txt").read_text() == "trabajo del humano\n"
    assert git(git_repo, "rev-parse", "main") == base
    assert "nuevo.py" in git(git_repo, "show", "--stat", "factory/run-2")


def test_snapshot_reset_tree_hash_y_diff(git_repo):
    base = preflight(git_repo, "main")
    wt = create_worktree(git_repo, load_config(git_repo).worktrees_path, "run-3", base)
    assert wt.snapshot("nada") is None
    (wt.path / "a.py").write_text("a = 1\n")
    first = wt.snapshot("r1")
    before = wt.tree_hash()
    (wt.path / "a.py").write_text("a = 2\n")
    (wt.path / "basura.txt").write_text("x")
    assert wt.tree_hash() != before
    wt.reset_to(first)
    assert wt.tree_hash() == before and not (wt.path / "basura.txt").exists()
    (wt.path / "b.py").write_text("b = 1\n")
    wt.snapshot("r2")
    cumulative = wt.diff(base)
    assert "a.py" in cumulative and "b.py" in cumulative
    assert "a.py" not in wt.diff(first)


def test_eliminar_worktree_conserva_rama_y_diffstat(git_repo):
    config = load_config(git_repo)
    base = preflight(git_repo, "main")
    wt = create_worktree(git_repo, config.worktrees_path, "run-4", base)
    (wt.path / "a.py").write_text("a = 1\nb = 2\n")
    wt.snapshot("r1")
    remove_worktree(wt)
    assert not wt.path.exists()
    assert git(git_repo, "branch", "--list", "factory/run-4")
    files, lines, stat = diffstat(git_repo, base, "factory/run-4")
    assert files == ["a.py"] and lines == 2 and "a.py" in stat


def test_detecta_worktrees_huerfanos(git_repo):
    config = load_config(git_repo)
    base = preflight(git_repo, "main")
    create_worktree(git_repo, config.worktrees_path, "vivo", base)
    create_worktree(git_repo, config.worktrees_path, "muerto", base)
    orphans = orphan_worktrees(git_repo, config.worktrees_path, active={"vivo"})
    assert [p.name for p in orphans] == ["muerto"]
