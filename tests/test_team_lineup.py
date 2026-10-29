"""Escenarios de `team-roster`: convocatoria determinista (`factory team lineup`)."""

import json
import subprocess
from pathlib import Path

from conftest import init_git_repo
from test_team_roster import write_agent, write_d2

from factory.cli import main
from factory.team.lineup import SIN_PARTIDO


def _lineup(root: Path, *args: str) -> int:
    return main(["--root", str(root), "team", "lineup", *args])


def _lineup_json(root: Path, capsys, *args: str) -> dict:
    assert _lineup(root, *args, "--json") == 0
    return json.loads(capsys.readouterr().out)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _repo_con_equipo(tmp_path: Path) -> Path:
    """Repo git con la plantilla D2 versionada y el árbol limpio."""
    root = init_git_repo(tmp_path / "repo")
    write_d2(root)
    _commit_all(root, "equipo")
    return root


def _names(items: list[dict]) -> list[str]:
    return [item["name"] for item in items]


# --------------------------------------------------------------------- Entradas de la convocatoria


def test_rutas_desde_git(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n")
    _commit_all(root, "src/a.py en main")
    _git(root, "checkout", "-q", "-b", "feat")
    (root / "src" / "a.py").write_text("x = 2\n")
    _commit_all(root, "modifica src/a.py")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a():\n    pass\n")  # no versionado

    data = _lineup_json(root, capsys, "--base", "main")
    assert data["base"] == "main"
    assert data["rutas"] == ["src/a.py", "tests/test_a.py"]
    assert data["peticion"] is False
    motivos = {c["name"]: c["motivo"] for c in data["convocados"]}
    assert motivos["qa"] == "rutas: src/a.py, tests/test_a.py"
    assert motivos["metricas"] == "rutas: src/a.py, tests/test_a.py"
    assert motivos["seguridad"] == "rutas: src/a.py, tests/test_a.py"
    assert motivos["revisor-pr"] == "siempre"
    assert set(motivos) == {"qa", "metricas", "seguridad", "revisor-pr"}


def test_rutas_por_defecto_frente_a_head(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)
    (root / "README.md").write_text("cambiado\n")  # modificado sin commit
    (root / "docs").mkdir()
    (root / "docs" / "nuevo.md").write_text("# Nuevo\n")  # no versionado
    data = _lineup_json(root, capsys)
    assert data["base"] == "HEAD"
    assert data["rutas"] == ["README.md", "docs/nuevo.md"]
    assert set(_names(data["convocados"])) == {"documentador", "revisor-pr"}


def test_rutas_indicadas_con_paths_sin_git(tmp_path, capsys):
    write_d2(tmp_path)  # sin repo git: --paths evita git
    args = ("--paths", "./src/x.py", "src/x.py", "--base", "main", "--json")
    assert _lineup(tmp_path, *args) == 0
    captured = capsys.readouterr()
    assert "con --paths se ignora --base" in captured.err
    data = json.loads(captured.out)
    assert data["base"] is None
    assert data["rutas"] == ["src/x.py"]
    assert "qa" in _names(data["convocados"])


def test_renombrado_aporta_origen_y_destino(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    _commit_all(root, "test en main")
    _git(root, "checkout", "-q", "-b", "feat")
    (root / "antiguo").mkdir()
    _git(root, "mv", "tests/test_x.py", "antiguo/test_x.py")
    _commit_all(root, "mueve el test")
    data = _lineup_json(root, capsys, "--base", "main")
    assert data["rutas"] == ["antiguo/test_x.py", "tests/test_x.py"]
    assert "qa" in _names(data["convocados"])


def test_base_invalida(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)
    assert _lineup(root, "--base", "no-existe") == 2
    assert "referencia git no válida" in capsys.readouterr().err
    assert _lineup(root, "--base=--output=x") == 2  # sin inyección de opciones en git
    assert not (root / "x").exists()
    assert _lineup(root, "--base", "") == 2  # una variable vacía no se convierte en HEAD
    assert "referencia git no válida" in capsys.readouterr().err


def test_sin_git_ni_paths(tmp_path, capsys):
    write_d2(tmp_path)
    assert _lineup(tmp_path) == 2
    assert "no es un repositorio git" in capsys.readouterr().err


def test_root_en_el_directorio_git(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)
    assert _lineup(root / ".git") == 2
    assert "no es un repositorio git" in capsys.readouterr().err


def test_repo_sin_commits(tmp_path, capsys):
    root = init_git_repo(tmp_path / "repo", commit=False)
    write_d2(root)
    assert _lineup(root) == 2
    assert "aún no tiene commits" in capsys.readouterr().err


def test_peticion_desde_archivo(tmp_path, capsys):
    write_d2(tmp_path)
    peticion = tmp_path / "peticion.md"
    peticion.write_text("Exportar el informe en CSV.\n")
    data = _lineup_json(tmp_path, capsys, "--paths", "README.md", "--peticion-file", str(peticion))
    assert data["peticion"] is True
    assert "ingeniero-software" in _names(data["convocados"])
    assert _lineup(tmp_path, "--paths", "x", "--peticion-file", str(tmp_path / "falta.md")) == 2
    assert "no se puede leer la petición" in capsys.readouterr().err


# ------------------------------------------------------------------------ Reglas de convocatoria


def test_cambio_solo_en_documentacion(tmp_path, capsys):
    write_d2(tmp_path)
    data = _lineup_json(tmp_path, capsys, "--paths", "docs/harness/roles.md")
    assert data["peticion"] is False
    motivos = {c["name"]: c["motivo"] for c in data["convocados"]}
    assert motivos == {"documentador": "rutas: docs/harness/roles.md", "revisor-pr": "siempre"}
    no_convocados = _names(data["no_convocados"])
    assert "qa" in no_convocados and "metricas" in no_convocados
    assert set(no_convocados) == {"seguridad", "qa", "metricas", "producto", "ingeniero-software"}


def test_peticion_de_producto_sin_cambios(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)  # árbol limpio: no hay rutas cambiadas
    data = _lineup_json(root, capsys, "--peticion", "exportar el informe en CSV")
    assert data["rutas"] == [] and data["peticion"] is True
    motivos = {c["name"]: c["motivo"] for c in data["convocados"]}
    assert motivos == {
        "revisor-pr": "siempre",
        "producto": "peticion",
        "ingeniero-software": "peticion",
    }


def test_el_tecnico_no_se_convoca(tmp_path, capsys):
    write_d2(tmp_path)
    data = _lineup_json(tmp_path, capsys, "--paths", ".claude/agents/tecnico.md")
    assert "tecnico" not in _names(data["convocados"]) + _names(data["no_convocados"])
    assert "seguridad" in _names(data["convocados"])


def test_motivo_cita_hasta_tres_rutas(tmp_path, capsys):
    write_d2(tmp_path)
    paths = ["src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py"]
    data = _lineup_json(tmp_path, capsys, "--paths", *paths)
    qa = next(c for c in data["convocados"] if c["name"] == "qa")
    assert qa == {
        "name": "qa",
        "dorsal": 2,
        "posicion": "lateral-derecho",
        "tipo": "revisor",
        "motivo": "rutas: src/a.py, src/b.py, src/c.py (+2 más)",
    }


def test_motivo_combina_rutas_y_peticion(tmp_path, capsys):
    write_d2(tmp_path)
    data = _lineup_json(
        tmp_path, capsys, "--paths", "openspec/changes/x/design.md", "--peticion", "algo"
    )
    producto = next(c for c in data["convocados"] if c["name"] == "producto")
    assert producto["motivo"] == "rutas: openspec/changes/x/design.md; peticion"


def test_lineup_en_texto(tmp_path, capsys):
    write_d2(tmp_path)
    assert _lineup(tmp_path, "--paths", "src/x.py", "--peticion", "exportar CSV") == 0
    out = capsys.readouterr().out
    assert "Convocatoria sugerida" in out
    assert "Rutas (1, indicadas con --paths): src/x.py" in out
    assert "Técnico: tecnico" in out
    assert "qa (revisor) — rutas: src/x.py" in out
    assert "ingeniero-software (constructor) — peticion" in out
    assert "No convocados (1):" in out and "documentador" in out.split("No convocados")[1]


def test_lineup_con_errores_sigue_con_los_validos(tmp_path, capsys):
    write_d2(tmp_path)
    write_agent(tmp_path, "metricas", tipo="revisor", dorsal=5, tools="Read, Write")
    assert _lineup(tmp_path, "--paths", "src/x.py", "--json") == 0
    captured = capsys.readouterr()
    assert ".claude/agents/metricas.md: un revisor es de solo lectura" in captured.err
    data = json.loads(captured.out)
    names = _names(data["convocados"]) + _names(data["no_convocados"])
    assert "metricas" not in names and "qa" in _names(data["convocados"])


# ---------------------------------------------------------------------------------- Sin partido


def test_nada_que_jugar(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)
    assert _lineup(root) == 0
    out = capsys.readouterr().out
    assert out.strip() == SIN_PARTIDO
    assert "no hay partido" in out
    data = _lineup_json(root, capsys)
    assert data["rutas"] == [] and data["peticion"] is False
    assert data["convocados"] == []
    assert len(data["no_convocados"]) == 7


def test_peticion_en_blanco_no_cuenta(tmp_path, capsys):
    root = _repo_con_equipo(tmp_path)
    assert _lineup(root, "--peticion", "   ") == 0
    assert capsys.readouterr().out.strip() == SIN_PARTIDO
