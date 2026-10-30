"""`factory land`: integración de una ejecución en la rama principal (spec run-landing).

Solo la invoca un humano. Construye el merge exacto de la rama sobre la punta actual de la
rama principal en un worktree temporal fuera del repo, lo verifica y solo entonces avanza la
rama principal a ese commit con `--ff-only`. Nunca ejecuta comandos de red (ni fetch ni push).
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from factory import artifacts
from factory.brain.daily import versioned_relatives
from factory.config import Config
from factory.gitops import Worktree, name_status, split_z
from factory.goal import parse_goal_text
from factory.inbox import Inbox, InboxError
from factory.protection import violations
from factory.state import COMPLETED, RunStore
from factory.util import GitError, atomic_write_text, git
from factory.verify import run_criteria


class LandError(RuntimeError):
    pass


@dataclass
class LandResult:
    run_id: str
    merge_commit: str
    main_before: str
    dry_run: bool
    checks_path: Path
    branch_deleted: bool = False


def _dirty_tracked(root: Path) -> list[str]:
    status = git(root, "status", "--porcelain", "--untracked-files=no")
    return [line[3:] for line in status.splitlines() if line.strip()]


def _current_branch(root: Path) -> str:
    proc = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _check_main_checkout(root: Path, main_branch: str, brain_rels: list[str] | None = None) -> None:
    dirty = _dirty_tracked(root)
    if dirty:
        shown = ", ".join(dirty[:5]) + (" …" if len(dirty) > 5 else "")
        hint = ""
        if any(p.startswith(f"{rel}/") for rel in brain_rels or [] for p in dirty):
            hint = (
                " Si son notas del cerebro diario o el mapa de la biblioteca, versiónalos con "
                "`factory brain commit`."
            )
        raise LandError(
            f"El checkout principal tiene cambios sin commitear ({shown}). Haz commit o "
            f"`git stash` antes de integrar.{hint}"
        )
    current = _current_branch(root)
    if current != main_branch:
        raise LandError(
            f"El checkout principal está en '{current or 'HEAD desacoplado'}', no en "
            f"'{main_branch}'. Cambia con `git switch {main_branch}`."
        )


def _remove_temp(root: Path, path: Path) -> None:
    git(root, "worktree", "remove", "--force", str(path), check=False)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    git(root, "worktree", "prune", check=False)


def land(
    config: Config,
    run_id: str,
    dry_run: bool = False,
    delete_branch: bool = False,
    echo: Callable[[str], None] = print,
) -> LandResult:
    root, main_branch = config.root, config.loop.main_branch
    store = RunStore(config.state_path)
    run_dir = store.run_dir(run_id)
    if not (run_dir / "state.json").exists():
        raise LandError(f"No existe la ejecución '{run_id}' en {store.runs_dir}")
    state = store.load(run_id)
    if state.landed_commit:
        raise LandError(f"'{run_id}' ya fue integrada en {state.landed_commit[:10]}.")
    if state.status != COMPLETED:
        raise LandError(
            f"'{run_id}' terminó '{state.status}', no completed: no se integra. Si hay que "
            f"continuarla, usa `factory goal rework {run_id} --answer …`."
        )
    branch_proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{state.branch}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if branch_proc.returncode != 0:
        raise LandError(f"La rama {state.branch} de la ejecución no existe.")
    branch_tip = branch_proc.stdout.strip()
    brain_rels = versioned_relatives(config)
    _check_main_checkout(root, main_branch, brain_rels)
    main_tip = git(root, "rev-parse", main_branch)

    goal_copy = run_dir / "goal.md"
    goal = parse_goal_text(goal_copy.read_text(encoding="utf-8"), config.loop, goal_copy)
    temp = config.worktrees_path / f"land-{run_id}"
    _remove_temp(root, temp)
    temp.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "-q", "--detach", str(temp), main_tip)
    wt = Worktree(root=root, path=temp, branch="", base=main_tip)
    checks_path = run_dir / "land" / "checks.md"
    try:
        message = f"factory: integrar {run_id} ({goal.id})"
        merge = subprocess.run(
            ["git", *wt.identity(), "merge", "--no-ff", "--no-edit", "-m", message, state.branch],
            cwd=temp,
            capture_output=True,
            text=True,
        )
        if merge.returncode != 0:
            conflicts = split_z(wt.git("diff", "--name-only", "-z", "--diff-filter=U", strip=False))
            wt.git("merge", "--abort", check=False)
            atomic_write_text(
                checks_path,
                artifacts.render_land_checks(
                    "FAIL", "", main_tip, branch_tip, None, [], conflicts or ["(desconocido)"]
                ),
            )
            detail = ", ".join(conflicts) or merge.stderr.strip()[:300]
            raise LandError(
                f"Conflicto al integrar {state.branch} sobre {main_branch}: {detail}. "
                f"{main_branch} no cambió."
            )
        merge_commit = wt.head()
        verification = run_criteria(goal.acceptance, temp, config.loop.verify_timeout_min * 60)
        protection = goal.protection_for(
            root, config.loop.protected_paths, config.effective_verify_command()
        )
        merge_base = git(root, "merge-base", main_tip, branch_tip)
        found = [str(v) for v in violations(name_status(root, merge_base, branch_tip), protection)]
        passed = verification.passed and not found
        atomic_write_text(
            checks_path,
            artifacts.render_land_checks(
                "PASS" if passed else "FAIL",
                merge_commit,
                main_tip,
                branch_tip,
                verification,
                found,
                [],
            ),
        )
        if not passed:
            reasons = [f"criterio fallido: {n}" for n in verification.failed] + [
                f"ruta protegida: {v}" for v in found
            ]
            raise LandError(
                f"La verificación del merge falló ({'; '.join(reasons)}). {main_branch} no "
                f"cambió. Informe: {checks_path}"
            )
        if dry_run:
            echo(f"Integración posible: el merge {merge_commit[:10]} pasa la verificación.")
            return LandResult(run_id, merge_commit, main_tip, True, checks_path)

        if git(root, "rev-parse", main_branch) != main_tip:
            raise LandError(
                f"{main_branch} cambió durante la verificación; vuelve a ejecutar `factory land`."
            )
        _check_main_checkout(root, main_branch, brain_rels)
        try:
            git(root, "merge", "--ff-only", "-q", merge_commit)
        except GitError as exc:
            raise LandError(f"No se pudo avanzar {main_branch}: {exc}") from exc
    finally:
        _remove_temp(root, temp)

    state.landed_commit = merge_commit
    store.save(state)
    atomic_write_text(run_dir / "decision.md", artifacts.render_decision(state))
    try:
        Inbox(config.state_path).ack(
            run_id, resolution=f"integrada en {main_branch} ({merge_commit[:10]})"
        )
    except InboxError:
        pass
    deleted = False
    if delete_branch:
        git(root, "branch", "-d", state.branch, check=False)  # -d: solo si ya está integrada
        deleted = not git(root, "branch", "--list", state.branch)
    echo(f"{main_branch} → {merge_commit[:10]} (integrada {run_id}; sin push)")
    return LandResult(run_id, merge_commit, main_tip, False, checks_path, deleted)
