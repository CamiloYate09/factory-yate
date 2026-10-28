"""Integración: `factory init` + `factory doctor` sobre un repositorio temporal (8.3)."""

import json
import subprocess

from conftest import init_git_repo

from factory.cli import main


def test_init_y_doctor_pasan_todas_las_criticas(tmp_path, capsys):
    repo = init_git_repo(tmp_path / "otro-proyecto")
    assert main(["init", "--target", str(repo), "--commands", "true"]) == 0
    capsys.readouterr()
    assert main(["--root", str(repo), "doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    failed = [c for c in report["checks"] if c["severity"] == "critical" and not c["passed"]]
    assert report["ok"] and failed == []
    proc = subprocess.run(["./init.sh"], cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert main(["--root", str(repo), "features", "verify", "ejemplo-001"]) == 0


def test_plantilla_de_goal_generada_valida(tmp_path, capsys):
    repo = init_git_repo(tmp_path / "p")
    main(["init", "--target", str(repo)])
    capsys.readouterr()
    assert main(["--root", str(repo), "goal", "validate", str(repo / "goals/_template.md")]) == 0
