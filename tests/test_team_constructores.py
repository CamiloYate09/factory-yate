"""Constructores del equipo ideal: ingeniero-software (#9) y documentador (#3) (6.1-6.2).

Comprueban el contrato del prompt (D2/D8 y secciones obligatorias). La conducta real del
documentador se comprueba aparte con una prueba e2e en haiku (tarea 6.2).
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude" / "agents"
INGENIERO = AGENTS / "ingeniero-software.md"
DOCUMENTADOR = AGENTS / "documentador.md"

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n(.*)\Z", re.DOTALL)

ESPERADO = {
    INGENIERO: {
        "dorsal": 9,
        "model": "sonnet",
        "convocatoria": "peticion",
        "tools": {"Read", "Edit", "Write", "Glob", "Grep", "Bash"},
    },
    DOCUMENTADOR: {
        "dorsal": 3,
        "model": "sonnet",
        "convocatoria": (
            "src/factory/cli.py, src/factory/config.py, factory.toml, docs/**, "
            "README.md, AGENTS.md, CLAUDE.md"
        ),
        "tools": {"Read", "Edit", "Write", "Glob", "Grep"},
    },
}


def _partes(path: Path) -> tuple[dict, str]:
    texto = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(texto)
    assert match, f"{path.name}: falta el frontmatter YAML entre líneas '---'"
    meta = yaml.safe_load(match.group(1))
    assert isinstance(meta, dict), f"{path.name}: el frontmatter no es un mapa"
    return meta, match.group(2)


def _frontmatter(path: Path) -> dict:
    return _partes(path)[0]


def _cuerpo(path: Path) -> str:
    return _partes(path)[1]


def _tools(meta: dict) -> set[str]:
    assert isinstance(meta["tools"], str), "tools debe ser una cadena separada por comas (D8)"
    return {tool.strip() for tool in meta["tools"].split(",") if tool.strip()}


def _regla(cuerpo: str, *fragmentos: str) -> bool:
    """Alguna línea del cuerpo contiene todos los fragmentos (sin distinguir mayúsculas)."""
    buscados = [fragmento.lower() for fragmento in fragmentos]
    return any(all(f in linea.lower() for f in buscados) for linea in cuerpo.splitlines())


@pytest.mark.parametrize("path", list(ESPERADO), ids=lambda p: p.stem)
def test_frontmatter_de_constructor(path):
    meta = _frontmatter(path)
    esperado = ESPERADO[path]
    assert meta["name"] == path.stem
    assert type(meta["dorsal"]) is int
    assert meta["dorsal"] == esperado["dorsal"]
    assert meta["tipo"] == "constructor"
    assert meta["model"] == esperado["model"]
    assert meta["convocatoria"] == esperado["convocatoria"]
    assert isinstance(meta["description"], str) and meta["description"].strip()
    assert "\n" not in meta["description"].strip()


@pytest.mark.parametrize("path", list(ESPERADO), ids=lambda p: p.stem)
def test_herramientas_de_constructor(path):
    tools = _tools(_frontmatter(path))
    assert "Agent" not in tools, "un constructor no invoca subagentes"
    assert tools == ESPERADO[path]["tools"]


def test_documentador_sin_bash():
    assert "Bash" not in _tools(_frontmatter(DOCUMENTADOR))


def test_cuerpo_del_ingeniero():
    cuerpo = _cuerpo(INGENIERO)
    for seccion in ("## Qué recibes", "## Reglas", "## Cómo trabajas", "## Formato de salida"):
        assert seccion in cuerpo, seccion
    for texto in (
        "## Jugador: ingeniero-software (#9)",
        "Informe del constructor",
        "feature_list.json",
        "status",
        "evidence",
        "debilit",
        "./scripts/check.sh",
        "WIP",
    ):
        assert texto in cuerpo, texto


@pytest.mark.parametrize(
    "fragmentos",
    [
        ("WIP", "alcance"),
        ("nunca", "status", "evidence", "feature_list.json"),
        ("no ejecutes", "factory features verify"),
        ("no debilites", "skip"),
        ("no cambies", "./scripts/check.sh", "ruff/pytest"),
        ("nunca", "push", "merge", "PR"),
        ("bypassPermissions",),
        ("no edites", ".claude/agents/**", ".claude/skills/**"),
        ("openspec/specs/",),
    ],
    ids=lambda fragmentos: fragmentos[-1],
)
def test_reglas_del_ingeniero(fragmentos):
    assert _regla(_cuerpo(INGENIERO), *fragmentos), fragmentos


def test_el_documentador_no_toca_codigo():
    """Escenario "El documentador no toca código" (contrato del prompt)."""
    cuerpo = _cuerpo(DOCUMENTADOR)
    for seccion in (
        "## Qué recibes",
        "## Reglas",
        "## Modo informe",
        "## Checklist",
        "## Formato de salida",
    ):
        assert seccion in cuerpo, seccion
    for texto in ("## Jugador: documentador (#3)", "*.md", "nunca código ni tests", "Modo informe"):
        assert texto in cuerpo, texto
    assert _regla(cuerpo, "solo", "*.md", "nunca código ni tests")
    assert _regla(
        cuerpo,
        "tampoco",
        "feature_list.json",
        "progress.md",
        "openspec/",
        ".claude/agents/**",
        ".claude/skills/**",
    )
    assert _regla(cuerpo, "no edites nada")
