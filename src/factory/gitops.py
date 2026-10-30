"""Operaciones git del loop: preflight, worktrees fuera del repo, instantáneas y reversiones."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from factory.util import GitError, git

BRANCH_PREFIX = "factory/"
FALLBACK_IDENTITY = ("-c", "user.name=factory", "-c", "user.email=factory@localhost")


class PreflightError(RuntimeError):
    pass


def preflight(root: Path, main_branch: str) -> str:
    """Comprueba que hay un commit en la rama principal y limpia worktrees huérfanos de git."""
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True, text=True
    )
    if inside.returncode != 0:
        raise PreflightError(f"{root} no es un repositorio git.")
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{main_branch}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise PreflightError(
            f"La rama '{main_branch}' no tiene commits: crea un commit inicial antes de lanzar un "
            "loop (los worktrees de cada ejecución parten de ese commit)."
        )
    git(root, "worktree", "prune")
    return proc.stdout.strip()


def orphan_worktrees(root: Path, worktrees_dir: Path, active: set[str]) -> list[Path]:
    """Worktrees de factory registrados en git cuya ejecución ya no está activa."""
    output = git(root, "worktree", "list", "--porcelain", check=False)
    paths = [
        Path(line.split(" ", 1)[1]) for line in output.splitlines() if line.startswith("worktree ")
    ]
    base = worktrees_dir.resolve()
    return [p for p in paths if p.resolve().parent == base and p.name not in active]


@dataclass
class Worktree:
    root: Path
    path: Path
    branch: str
    base: str  # commit base de la ejecución (para diffs acumulados y rutas protegidas)
    start: str = ""  # commit del que parte la rama; = base salvo en un retrabajo

    def __post_init__(self) -> None:
        self.start = self.start or self.base

    def git(self, *args: str, check: bool = True) -> str:
        return git(self.path, *args, check=check)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def identity(self) -> tuple[str, ...]:
        has_name = self.git("config", "user.name", check=False)
        has_email = self.git("config", "user.email", check=False)
        return () if has_name and has_email else FALLBACK_IDENTITY

    def snapshot(self, message: str) -> str | None:
        """Commit de todo lo cambiado (None si no hay cambios). Lo hace el orquestador."""
        self.git("add", "-A")
        if not self.git("status", "--porcelain"):
            return None
        self.git(*self.identity(), "commit", "-q", "--no-verify", "-m", message)
        return self.head()

    def reset_to(self, commit: str) -> None:
        """Vuelve exactamente a `commit`: descarta cambios y archivos nuevos no ignorados."""
        self.git("reset", "-q", "--hard", commit)
        self.git("clean", "-q", "-fd")

    def changed_files(self, since: str) -> list[str]:
        tracked = split_z(self.git("diff", "--name-only", "-z", since))
        untracked = split_z(self.git("ls-files", "-z", "--others", "--exclude-standard"))
        return sorted({p for p in tracked + untracked if p})

    def tree_hash(self) -> str:
        """Huella del estado del árbol: detecta cualquier escritura (p. ej. del checker)."""
        status = self.git("status", "--porcelain=v1", "--untracked-files=all")
        diff = self.git("diff", "HEAD")
        return hashlib.sha256((self.head() + status + diff).encode()).hexdigest()

    def diff(self, since: str, until: str = "HEAD") -> str:
        return self.git("diff", f"{since}..{until}")

    def name_status(self, since: str, until: str = "HEAD") -> list[tuple[str, str, str | None]]:
        return name_status(self.path, since, until)


def split_z(output: str) -> list[str]:
    """Rutas de una salida `-z` de git: sin comillas ni escapes, aunque lleven tildes."""
    return [item for item in output.split("\0") if item]


def name_status(cwd: Path, since: str, until: str) -> list[tuple[str, str, str | None]]:
    """(estado, ruta, ruta nueva) de `git diff --name-status -M`; en renombrados, la ruta es la
    original y la nueva va aparte. Con `-z`, para que las rutas con tildes no lleguen entre
    comillas y escapen a las rutas protegidas."""
    tokens = split_z(git(cwd, "diff", "--name-status", "-M", "-z", f"{since}..{until}"))
    entries: list[tuple[str, str, str | None]] = []
    i = 0
    while i + 1 < len(tokens):
        status = tokens[i]
        if status[:1] in ("R", "C") and i + 2 < len(tokens):
            entries.append((status, tokens[i + 1], tokens[i + 2]))
            i += 3
        else:
            entries.append((status, tokens[i + 1], None))
            i += 2
    return entries


def create_worktree(
    root: Path, worktrees_dir: Path, run_id: str, base: str, start_point: str | None = None
) -> Worktree:
    """Worktree y rama nuevos. `start_point` (por defecto `base`) permite partir de la punta de
    otra rama sin perder el commit base original."""
    path = worktrees_dir / run_id
    branch = BRANCH_PREFIX + run_id
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    start = start_point or base
    git(root, "worktree", "add", "-q", "-b", branch, str(path), start)
    return Worktree(root=root, path=path, branch=branch, base=base, start=start)


def remove_worktree(worktree: Worktree) -> None:
    """Elimina el worktree y conserva la rama para revisión humana."""
    try:
        git(worktree.root, "worktree", "remove", "--force", str(worktree.path))
    except GitError:
        git(worktree.root, "worktree", "prune", check=False)


def diffstat(root: Path, base: str, branch: str) -> tuple[list[str], int, str]:
    """(archivos cambiados, líneas añadidas+eliminadas, `git diff --stat`) entre base y rama."""
    numstat = git(root, "diff", "--numstat", f"{base}..{branch}", check=False)
    files, lines = [], 0
    for row in numstat.splitlines():
        added, deleted, name = row.split("\t", 2)
        files.append(name)
        lines += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
    stat = git(root, "diff", "--stat", f"{base}..{branch}", check=False)
    return files, lines, stat
