from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def make_feature(fid: str, status: str = "not_started", **overrides) -> dict:
    feature = {
        "id": fid,
        "priority": 1,
        "area": "core",
        "title": f"Feature {fid}",
        "user_visible_behavior": "Algo observable.",
        "status": status,
        "verification": ["true"],
        "manual_checks": [],
        "evidence": [],
        "notes": "",
    }
    feature.update(overrides)
    return feature


def feature_doc(*features: dict) -> dict:
    return {"project": "demo", "last_updated": "2026-01-01", "features": list(features)}


def write_features(root: Path, *features: dict) -> Path:
    path = root / "feature_list.json"
    path.write_text(json.dumps(feature_doc(*features), indent=2), encoding="utf-8")
    return path


def init_git_repo(root: Path, commit: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    if commit:
        (root / "README.md").write_text("demo\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=root, check=True)
    return root


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    return init_git_repo(tmp_path / "repo")


def make_harness(root: Path) -> Path:
    """Crea un harness mínimo completo (todas las comprobaciones de doctor pasan)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "verificacion.md").write_text("# Verificación\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "# AGENTS\n\nVerificación: `./scripts/check.sh`\n\n[Verificación](docs/verificacion.md)\n",
        encoding="utf-8",
    )
    (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    write_features(root, make_feature("f-1", priority=1), make_feature("f-2", priority=2))
    (root / "progress.md").write_text("# Progreso\n", encoding="utf-8")
    (root / "session-handoff.md").write_text("# Handoff\n", encoding="utf-8")
    (root / "docs" / "harness").mkdir(exist_ok=True)
    (root / "docs" / "harness" / "clean-state-checklist.md").write_text("- [ ] x\n")
    scripts = root / "scripts"
    scripts.mkdir(exist_ok=True)
    for script in (scripts / "check.sh", root / "init.sh"):
        script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
    return root


GOAL_TEMPLATE = """---
id: demo
objective: Crear los archivos pedidos
{extra}acceptance:
{criteria}scope:
  allow: ["**"]
  deny: ["prohibido/**"]
stop:
  max_rounds: {max_rounds}
  max_budget_usd: {budget}
  no_progress_rounds: {no_progress}
---
Crea los archivos.
"""


def make_loop_repo(tmp_path: Path, features: tuple = ()) -> Path:
    """Repo git con commit, prompts de roles y (opcional) lista de features."""
    root = init_git_repo(tmp_path / "repo", commit=False)
    (root / "prompts").mkdir()
    (root / "prompts" / "maker.md").write_text("Eres el maker de prueba.\n")
    (root / "prompts" / "checker.md").write_text("Eres el checker de prueba.\n")
    (root / ".gitignore").write_text(".factory/\n")
    if features:
        write_features(root, *features)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=root, check=True)
    return root


def write_goal(
    root: Path,
    files: tuple[str, ...] = ("a.txt",),
    max_rounds: int = 5,
    budget: float = 10,
    no_progress: int = 3,
    extra: str = "",
    criteria: str | None = None,
) -> Path:
    if criteria is None:
        criteria = "".join(f"  - name: {f}\n    run: test -f {f}\n" for f in files)
    text = GOAL_TEMPLATE.format(
        extra=extra,
        criteria=criteria,
        max_rounds=max_rounds,
        budget=budget,
        no_progress=no_progress,
    )
    path = root / "goals" / "demo.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
