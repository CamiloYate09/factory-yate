"""Escenarios de `agent-backends`: herramientas confinadas del backend Strands (sin `strands`)."""

import subprocess
import sys
import threading
import time

import pytest

from factory.agents.strands_tools import (
    PathPolicy,
    ShellPolicy,
    ToolError,
    UntranslatableTools,
    plan_tools,
)
from factory.config import MANDATORY_DENIED, brain_denials, default_roles


@pytest.fixture
def mundo(tmp_path):
    """Repo principal, worktree del maker y un cerebro, como en una ronda real."""
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    brain = tmp_path / "repo" / "brain-diario"
    for path in (repo, worktree, brain):
        path.mkdir(parents=True)
    (repo / "secreto.txt").write_text("del repo principal\n")
    (worktree / "feature_list.json").write_text("{}\n")
    (worktree / "src").mkdir()
    (worktree / "src" / "app.py").write_text("def saludo():\n    return 'hola'\n")
    (brain / "nota.md").write_text("conocimiento\n")
    return repo, worktree, brain


def _maker(worktree, brain):
    role = default_roles()["maker"]
    return plan_tools(
        role.allowed_tools, role.denied_tools + brain_denials([brain]), worktree, [brain]
    )


def _checker(worktree, brain=None):
    role = default_roles()["checker"]
    return plan_tools(role.allowed_tools, role.denied_tools, worktree, [brain] if brain else [])


# ------------------------------------------------------------------ confinamiento de rutas


def test_escritura_fuera_del_worktree(mundo):
    repo, worktree, brain = mundo
    tools = _maker(worktree, brain)
    for destino in (repo / "secreto.txt", "../repo/secreto.txt", str(repo / "nuevo.txt")):
        with pytest.raises(ToolError, match="fuera"):
            tools.write(str(destino), "pisado")
    assert (repo / "secreto.txt").read_text() == "del repo principal\n"
    assert not (repo / "nuevo.txt").exists()


def test_ruta_denegada_por_rol(mundo):
    _, worktree, brain = mundo
    tools = _maker(worktree, brain)
    with pytest.raises(ToolError, match="protegido"):
        tools.edit("feature_list.json", "{}", '{"status": "passing"}')
    with pytest.raises(ToolError, match="protegido"):
        tools.write(str(worktree / "feature_list.json"), "{}")
    assert (worktree / "feature_list.json").read_text() == "{}\n"


def test_cerebro_de_solo_lectura(mundo):
    _, worktree, brain = mundo
    tools = _maker(worktree, brain)
    assert "conocimiento" in tools.read(str(brain / "nota.md"))
    with pytest.raises(ToolError):
        tools.write(str(brain / "nota.md"), "pisado")
    with pytest.raises(ToolError):
        tools.edit(str(brain / "nota.md"), "conocimiento", "pisado")
    assert (brain / "nota.md").read_text() == "conocimiento\n"


def test_cerebro_dentro_del_directorio_de_trabajo_sigue_siendo_de_solo_lectura(mundo):
    repo, _, brain = mundo
    paths = PathPolicy(repo, [brain])
    with pytest.raises(ToolError):
        paths.check_write(brain / "nota.md")
    assert paths.check_write(repo / "otro.txt")


def test_enlace_simbolico_que_sale_del_worktree(mundo):
    repo, worktree, brain = mundo
    (worktree / "atajo").symlink_to(repo)
    (worktree / "secreto-enlazado.txt").symlink_to(repo / "secreto.txt")
    tools = _maker(worktree, brain)
    with pytest.raises(ToolError):
        tools.write("atajo/secreto.txt", "pisado")
    with pytest.raises(ToolError):
        tools.read("atajo/secreto.txt")
    with pytest.raises(ToolError):
        tools.edit("secreto-enlazado.txt", "repo", "pisado")
    assert (repo / "secreto.txt").read_text() == "del repo principal\n"
    assert "secreto" not in tools.glob("**/*")
    assert "del repo principal" not in tools.grep("principal")


def test_lectura_fuera_de_las_raices(mundo, tmp_path):
    _, worktree, _ = mundo
    tools = _checker(worktree)
    with pytest.raises(ToolError, match="lectura denegada"):
        tools.read(str(tmp_path / "repo" / "secreto.txt"))
    with pytest.raises(ToolError, match="lectura denegada"):
        tools.grep("principal", path=str(tmp_path / "repo"))


def test_read_denegado_por_regla(mundo):
    _, worktree, _ = mundo
    (worktree / ".env").write_text("TOKEN=x\n")
    tools = plan_tools(["Read", "Grep", "Glob"], ["Read(.env)"], worktree)
    with pytest.raises(ToolError):
        tools.read(".env")
    assert ".env" not in tools.glob("*")
    assert "TOKEN" not in tools.grep("TOKEN")


# ------------------------------------------------------------------ shell


def test_push_del_maker(mundo):
    _, worktree, brain = mundo
    tools = _maker(worktree, brain)
    with pytest.raises(ToolError):
        tools.shell("git push origin main")


def test_encadenamiento_para_eludir_el_prefijo(mundo):
    _, worktree, brain = mundo
    tools = _maker(worktree, brain)
    for command in (
        "git status; rm -rf src",
        "git status && rm -rf src",
        "git status | sh",
        "git diff > src/app.py",
        "git status $(rm -rf src)",
        "git status `rm -rf src`",
        "git status\nrm -rf src",
    ):
        with pytest.raises(ToolError, match="rechazado"):
            tools.shell(command)
    assert (worktree / "src" / "app.py").exists()


def test_git_status_permitido_se_ejecuta_en_el_cwd(mundo):
    _, worktree, brain = mundo
    subprocess.run(["git", "init", "-q"], cwd=worktree, check=True)
    tools = _maker(worktree, brain)
    salida = tools.shell("git status --porcelain")
    assert salida.startswith("código de salida: 0")
    assert "src/" in salida  # el estado es el del worktree, no el del proceso


def test_prefijo_comparado_por_tokens(tmp_path):
    shell = ShellPolicy(tmp_path, [(("git", "diff"), True), (("git", "status"), False)])
    assert shell.check("git diff --stat") == ["git", "diff", "--stat"]
    assert shell.check("git status") == ["git", "status"]
    for command in ("git diffx", "git status --short", "git -C /tmp diff", "rm -rf /"):
        with pytest.raises(ToolError):
            shell.check(command)


def test_denegacion_gana_al_permiso(tmp_path):
    shell = ShellPolicy(tmp_path, [(("git",), True)], [(("git", "push"), True)])
    assert shell.check("git log")
    with pytest.raises(ToolError, match="denegado"):
        shell.check("git push origin main")


def test_shell_usa_el_python_del_entorno(tmp_path):
    tools = plan_tools(["Bash(python -c:*)"], [], tmp_path)
    salida = tools.shell("python -c 'print(__import__(\"sys\").executable)'")
    assert sys.executable in salida
    # Los metacaracteres se rechazan también entre comillas: preferimos rechazar a interpretar.
    with pytest.raises(ToolError, match="rechazado"):
        tools.shell("python -c 'import sys; print(sys.executable)'")


# ------------------------------------------------------------------ traducción


def test_herramienta_sin_traduccion(tmp_path):
    with pytest.raises(UntranslatableTools) as exc:
        plan_tools(["Read", "NotebookEdit", "WebFetch", "mcp__x__y"], [], tmp_path)
    assert exc.value.names == ["NotebookEdit", "WebFetch", "mcp__x__y"]
    assert "NotebookEdit" in str(exc.value)


def test_bash_sin_prefijo_se_rechaza(tmp_path):
    with pytest.raises(UntranslatableTools, match="Bash"):
        plan_tools(["Read", "Bash"], [], tmp_path)


def test_permiso_con_ruta_se_rechaza(tmp_path):
    with pytest.raises(UntranslatableTools, match=r"Edit\(src/\*\*\)"):
        plan_tools(["Edit(src/**)"], [], tmp_path)


def test_checker_de_solo_lectura(mundo):
    _, worktree, brain = mundo
    tools = _checker(worktree, brain)
    assert tools.names == ["read", "glob", "grep"]
    assert tools.shell_policy is None
    assert set(tools.functions()) == {"read", "glob", "grep"}


def test_checker_con_escritura_permitida_sigue_de_solo_lectura(mundo):
    """Aunque un goal añada Edit o Bash al checker, sus denegaciones obligatorias ganan."""
    _, worktree, _ = mundo
    tools = plan_tools(
        ["Read", "Glob", "Grep", "Edit", "Write", "Bash(git diff:*)"],
        MANDATORY_DENIED["checker"],
        worktree,
    )
    assert tools.names == ["read", "glob", "grep"]


def test_maker_por_defecto(mundo):
    _, worktree, brain = mundo
    tools = _maker(worktree, brain)
    assert tools.names == ["read", "glob", "grep", "edit", "write", "shell"]


# ------------------------------------------------------------------ comportamiento


def test_read_numera_y_acota(mundo):
    _, worktree, _ = mundo
    tools = _checker(worktree)
    assert tools.read("src/app.py") == "     1\tdef saludo():\n     2\t    return 'hola'"
    assert tools.read("src/app.py", offset=2, limit=1) == "     2\t    return 'hola'"
    with pytest.raises(ToolError, match="no existe"):
        tools.read("src/otro.py")


def test_glob_y_grep(mundo):
    _, worktree, _ = mundo
    (worktree / ".git").mkdir()
    (worktree / ".git" / "config").write_text("hola\n")
    tools = _checker(worktree)
    assert tools.glob("**/*.py") == "src/app.py"
    assert tools.glob("*.json") == "feature_list.json"
    assert tools.grep("hola") == "src/app.py:2:    return 'hola'"  # .git se ignora
    assert tools.grep("HOLA", ignore_case=True, glob="**/*.py") == "src/app.py:2:    return 'hola'"
    assert tools.grep("nada-de-esto") == "(sin coincidencias)"
    with pytest.raises(ToolError, match="regular"):
        tools.grep("(")


def test_edit_y_write(mundo):
    _, worktree, brain = mundo
    tools = _maker(worktree, brain)
    tools.edit("src/app.py", "'hola'", "'adiós'")
    assert "'adiós'" in (worktree / "src" / "app.py").read_text()
    with pytest.raises(ToolError, match="no aparece"):
        tools.edit("src/app.py", "'hola'", "x")
    tools.write("src/nuevo/modulo.py", "X = 1\n")
    assert (worktree / "src" / "nuevo" / "modulo.py").read_text() == "X = 1\n"
    (worktree / "dup.txt").write_text("a a\n")
    with pytest.raises(ToolError, match="2 veces"):
        tools.edit("dup.txt", "a", "b")
    tools.edit("dup.txt", "a", "b", replace_all=True)
    assert (worktree / "dup.txt").read_text() == "b b\n"


def test_cancelacion_mata_el_comando_en_curso(tmp_path):
    cancel = threading.Event()
    tools = plan_tools(["Bash(python -c:*)"], [], tmp_path, shell_timeout_s=60, cancel=cancel)
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(ToolError, match="cancelada"):
        tools.shell("python -c \"__import__('time').sleep(1.5) or open('termino.txt', 'w')\"")
    assert time.monotonic() - started < 1.5
    time.sleep(2)
    assert not (tmp_path / "termino.txt").exists()


def test_el_shell_no_hereda_credenciales(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secreta")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secreta")
    tools = plan_tools(["Bash(python -c:*)"], [], tmp_path)
    salida = tools.shell(
        "python -c \"print(__import__('os').environ.get('ANTHROPIC_API_KEY', 'sin-clave'))\""
    )
    assert "sk-secreta" not in salida and "sin-clave" in salida
    monkeypatch.setenv("AWS_PROFILE", "perfil")
    salida = tools.shell(
        "python -c \"print(__import__('os').environ.get('AWS_PROFILE', 'sin-aws'))\""
    )
    assert "sin-aws" in salida


def test_escritura_en_git_denegada(mundo):
    _, worktree, brain = mundo
    (worktree / ".git").write_text("gitdir: /repo/.git/worktrees/x\n")
    tools = _maker(worktree, brain)
    for destino in (".git", ".GIT", "sub/.git/config", ".git/hooks/pre-commit"):
        with pytest.raises(ToolError, match="git"):
            tools.write(destino, "gitdir: /otro\n")
    assert (worktree / ".git").read_text() == "gitdir: /repo/.git/worktrees/x\n"


def test_mayusculas_no_eluden_las_denegaciones(mundo):
    _, worktree, brain = mundo
    (worktree / ".env").write_text("TOKEN=x\n")
    tools = plan_tools(
        ["Read", "Edit", "Write"],
        ["Read(.env)", "Edit(feature_list.json)", "Write(feature_list.json)"],
        worktree,
        [brain],
    )
    with pytest.raises(ToolError, match="protegido"):
        tools.edit("FEATURE_LIST.json", "{}", "x")
    with pytest.raises(ToolError, match="denegada"):
        tools.read(".ENV")
    with pytest.raises(ToolError):  # el cerebro está dentro del repo principal (mundo)
        PathPolicy(brain.parent, [brain]).check_write(brain.parent / "BRAIN-DIARIO" / "nota.md")
    assert (worktree / "feature_list.json").read_text() == "{}\n"


def test_regla_bash_ilegible_falla_cerrado(tmp_path):
    with pytest.raises(UntranslatableTools, match="comillas"):
        plan_tools(['Bash(echo "comillas:*)'], [], tmp_path)
    with pytest.raises(UntranslatableTools):
        plan_tools(["Bash(git status:*)"], ["Bash(git 'push:*)"], tmp_path)


GUARDA = """
import sys
from pathlib import Path
from factory.agents.strands_tools import ToolError, plan_tools

work = Path(sys.argv[1])
(work / ("a" * 45 + ".txt")).write_text("a" * 40 + "!\\n")
tools = plan_tools(["Grep", "Glob"], [], work)
tools.search_timeout_s = 0.5
try:
    {llamada}
except ToolError as exc:
    print(exc)
"""


@pytest.mark.parametrize(
    "llamada",
    [
        'tools.grep("(a+)+$")',
        'tools.glob("*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*b")',
        'tools.grep("a", glob="*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*a*b")',
    ],
)
def test_patron_costoso_se_detiene(tmp_path, llamada):
    """En un subproceso con tiempo límite externo: una regresión no debe colgar la suite."""
    salida = subprocess.run(
        [sys.executable, "-c", GUARDA.format(llamada=llamada), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert "demasiado costosa" in salida.stdout


def test_cancelacion_detiene_la_busqueda(tmp_path):
    (tmp_path / "f.txt").write_text("a" * 40 + "!\n")
    cancel = threading.Event()
    tools = plan_tools(["Grep"], [], tmp_path, cancel=cancel)
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(ToolError, match="cancelada"):
        tools.grep("(a+)+$")
    assert time.monotonic() - started < 5
