"""Escenarios de `harness-scaffolding`: `factory init`."""

import json
import os
import subprocess

from factory.cli import main
from factory.features import validate


def _init(target, *extra):
    return main(["init", "--target", str(target), *extra])


def test_repositorio_sin_harness(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
    assert _init(tmp_path) == 0
    out = capsys.readouterr().out
    expected = [
        "AGENTS.md",
        "CLAUDE.md",
        "feature_list.json",
        "progress.md",
        "session-handoff.md",
        "init.sh",
        "scripts/check.sh",
        "factory.toml",
        "prompts/maker.md",
        "prompts/checker.md",
        "prompts/intake.md",
        "goals/_template.md",
        "docs/harness/clean-state-checklist.md",
    ]
    for relative in expected:
        assert (tmp_path / relative).exists(), relative
        assert f"  - {relative}" in out
    assert "Verificación (pyproject.toml): python3 -m pytest -q, python3 -m ruff check ." in out
    assert "Marcadores pendientes de completar:" in out
    assert "AGENTS.md: busca 'TODO(factory)'" in out
    assert os.access(tmp_path / "init.sh", os.X_OK)
    assert os.access(tmp_path / "scripts" / "check.sh", os.X_OK)
    data = json.loads((tmp_path / "feature_list.json").read_text())
    assert validate(data) == []
    assert "{{" not in (tmp_path / "AGENTS.md").read_text()


def test_comandos_indicados_por_el_usuario(tmp_path):
    assert _init(tmp_path, "--commands", "true, echo verificado") == 0
    check = (tmp_path / "scripts" / "check.sh").read_text()
    assert "run_step true\nrun_step 'echo verificado'" in check
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "  - `true`\n  - `echo verificado`" in agents
    proc = subprocess.run(["./scripts/check.sh"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0 and "verificado" in proc.stdout


def test_archivo_de_instrucciones_existente_no_se_toca(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("mis instrucciones\n")
    assert _init(tmp_path) == 0
    assert (tmp_path / "AGENTS.md").read_text() == "mis instrucciones\n"
    out = capsys.readouterr().out
    assert "Omitidos (ya existían; usa --force para sobrescribir):\n  - AGENTS.md" in out


def test_force_sobrescribe(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("viejo\n")
    assert _init(tmp_path, "--force") == 0
    assert "viejo" not in (tmp_path / "AGENTS.md").read_text()
    assert "Sobrescritos (--force):\n  - AGENTS.md" in capsys.readouterr().out


def test_deteccion_makefile_y_package_json(tmp_path):
    from factory.scaffold import detect

    (tmp_path / "Makefile").write_text("setup:\n\techo\ncheck:\n\techo\n")
    detection = detect(tmp_path)
    assert detection.verify == ["make check"] and detection.install == "make setup"
    other = tmp_path / "js"
    other.mkdir()
    (other / "package.json").write_text('{"scripts": {"test": "x", "lint": "y"}}')
    assert detect(other).verify == ["npm test", "npm run lint"]


def test_sin_deteccion_la_verificacion_falla_explicitamente(tmp_path):
    assert _init(tmp_path) == 0
    proc = subprocess.run(["./scripts/check.sh"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 1 and "TODO(factory)" in proc.stderr


def test_agent_file_claude(tmp_path):
    assert _init(tmp_path, "--agent-file", "CLAUDE.md") == 0
    assert not (tmp_path / "AGENTS.md").exists()
    assert "## Restricciones duras" in (tmp_path / "CLAUDE.md").read_text()
    assert 'entry_file = "CLAUDE.md"' in (tmp_path / "factory.toml").read_text()


def test_init_sh_pyproject_usa_venv(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert _init(tmp_path) == 0
    text = (tmp_path / "init.sh").read_text()
    assert ".venv" in text and "VIRTUAL_ENV" in text
    assert "python3 -m pip install -e ." not in text
    assert "-m pip install -e ." in text
    assert text.index("export PATH") < text.index("exec ./scripts/check.sh")
    assert subprocess.run(["bash", "-n", "init.sh"], cwd=tmp_path).returncode == 0


def test_init_sh_venv_no_afecta_makefile_ni_package_json(tmp_path):
    make = tmp_path / "make"
    make.mkdir()
    (make / "Makefile").write_text("setup:\n\techo\ncheck:\n\techo\n")
    js = tmp_path / "js"
    js.mkdir()
    (js / "package.json").write_text('{"scripts": {"test": "x"}}')
    assert _init(make) == 0 and _init(js) == 0
    make_sh = (make / "init.sh").read_text()
    js_sh = (js / "init.sh").read_text()
    assert ".venv" not in make_sh and "make setup" in make_sh
    assert ".venv" not in js_sh and "npm install" in js_sh


def test_destino_inexistente(tmp_path, capsys):
    assert _init(tmp_path / "no-existe") == 2
    assert "No existe el directorio destino" in capsys.readouterr().err
