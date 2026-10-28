"""Escenarios de `harness-scaffolding` (auditoría) y de `agent-harness` (router corto)."""

import json

from conftest import make_feature, make_harness, write_features

from factory.cli import main


def _doctor(root, *extra):
    return main(["--root", str(root), "doctor", *extra])


def test_harness_completo(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    assert _doctor(root) == 0
    out = capsys.readouterr().out
    for subsystem in ("instrucciones", "estado", "verificacion", "alcance", "ciclo_de_vida"):
        assert f"{subsystem} (100%)" in out
    assert "[FAIL]" not in out


def test_falta_la_ruta_de_verificacion(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    (root / "scripts" / "check.sh").unlink()
    assert _doctor(root) == 1
    out = capsys.readouterr().out
    assert "[FAIL] [CRITICAL] Hay un comando único de verificación" in out
    assert "scripts/check.sh" in out


def test_subsistema_mas_debil_y_tres_acciones(tmp_path):
    root = make_harness(tmp_path / "repo")
    (root / "init.sh").unlink()
    (root / "session-handoff.md").unlink()
    (root / "docs" / "harness" / "clean-state-checklist.md").unlink()
    (root / "progress.md").unlink()
    from factory.config import load_config
    from factory.doctor import audit

    report = audit(load_config(root))
    assert report.weakest() == "ciclo_de_vida"
    actions = report.actions()
    assert len(actions) == 3
    assert "init.sh" in actions[0]  # crítica del subsistema más débil primero
    assert "progress.md" in actions[1]  # luego críticas de otros subsistemas


def test_consumo_desde_otro_proceso(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    (root / "progress.md").unlink()
    assert _doctor(root, "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    check = next(c for c in data["checks"] if c["id"] == "progress-exists")
    assert check == {**check, "subsystem": "estado", "severity": "critical", "passed": False}
    assert check["fix"]
    assert all({"subsystem", "severity", "passed", "fix"} <= c.keys() for c in data["checks"])


def test_archivo_de_entrada_excede_el_limite(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    body = "\n".join(f"línea {i}" for i in range(150))
    (root / "AGENTS.md").write_text(
        "# AGENTS\n`./scripts/check.sh`\n## Corta\nx\n## Muy larga\n" + body + "\n## Otra\n" + body,
        encoding="utf-8",
    )
    assert _doctor(root) == 1
    out = capsys.readouterr().out
    assert "[FAIL] [CRITICAL] AGENTS.md tiene 200 líneas o menos" in out
    assert "'## Muy larga'" in out


def test_enlace_roto(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    (root / "docs" / "verificacion.md").unlink()
    assert _doctor(root) == 1
    assert "docs/verificacion.md" in capsys.readouterr().out


def test_wip_y_passing_sin_evidencia(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    write_features(
        root,
        make_feature("f-1", "in_progress", priority=1),
        make_feature("f-2", "in_progress", priority=2),
        make_feature("f-3", "passing", priority=3),
    )
    assert _doctor(root) == 1
    out = capsys.readouterr().out
    assert "[FAIL] [CRITICAL] Como máximo una feature en in_progress" in out
    assert "f-3" in out
