"""Contrato de los revisores `qa`, `producto` y `revisor-pr` (team-match, D2/D3/D8)."""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
AGENTS = REPO / ".claude" / "agents"
SOLO_LECTURA = {"Read", "Grep", "Glob"}
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)

# name -> (dorsal, model, convocatoria)
REVISORES = {
    "qa": (2, "sonnet", "src/**, tests/**"),
    "producto": (6, "opus", "peticion, openspec/changes/**"),
    "revisor-pr": (4, "opus", "siempre"),
}
# Campos de cada hallazgo y secciones del formato común (D3).
CAMPOS_D3 = ("- Ubicación:", "- Descripción:", "- Evidencia:", "- Sugerencia:")
SECCIONES_D3 = ("## Veredicto", "## Hallazgos", "## Verificación recibida")


def _frontmatter(path: Path) -> tuple[dict, str]:
    """Devuelve el frontmatter YAML y el cuerpo de un agente."""
    coincidencia = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    assert coincidencia, f"{path.name}: falta el frontmatter"
    datos = yaml.safe_load(coincidencia.group(1))
    assert isinstance(datos, dict), f"{path.name}: frontmatter ilegible"
    return datos, coincidencia.group(2)


def _cuerpo(name: str) -> str:
    return _frontmatter(AGENTS / f"{name}.md")[1]


def _linea_con(cuerpo: str, fragmento: str) -> str:
    lineas = [linea for linea in cuerpo.splitlines() if fragmento in linea]
    assert lineas, f"no aparece {fragmento!r}"
    return lineas[0]


@pytest.mark.parametrize("name", sorted(REVISORES))
def test_frontmatter_del_revisor(name):
    dorsal, model, convocatoria = REVISORES[name]
    datos, _ = _frontmatter(AGENTS / f"{name}.md")
    assert datos["name"] == name
    assert type(datos["dorsal"]) is int
    assert datos["dorsal"] == dorsal
    assert datos["tipo"] == "revisor"
    assert datos["model"] == model
    assert datos["convocatoria"] == convocatoria
    # D8: `tools` es una cadena separada por comas, como en checker.md.
    assert isinstance(datos["tools"], str)
    herramientas = {tool.strip() for tool in datos["tools"].split(",") if tool.strip()}
    assert herramientas and herramientas <= SOLO_LECTURA
    # Un " #" sin comillas truncaría la descripción como comentario YAML.
    assert f"(#{dorsal})" in datos["description"]


@pytest.mark.parametrize("name", sorted(REVISORES))
def test_cabecera_del_jugador(name):
    dorsal = REVISORES[name][0]
    cuerpo = _cuerpo(name)
    cabecera = f"## Jugador: {name} (#{dorsal})"
    assert f"empieza exactamente con la línea `{cabecera}`" in cuerpo
    # La plantilla de salida arranca con la cabecera y sigue el formato del checker.
    plantilla = cuerpo[cuerpo.index("```\n" + cabecera) :]
    for seccion in SECCIONES_D3:
        assert seccion in plantilla
    for campo in CAMPOS_D3:
        assert campo in plantilla
    assert "exactamente una línea de veredicto" in cuerpo.lower()


@pytest.mark.parametrize("name", sorted(REVISORES))
def test_revision_sin_efectos(name):
    cuerpo = _cuerpo(name)
    assert "## Qué recibes" in cuerpo
    assert "solo lectura" in cuerpo
    assert "no ejecutes comandos" in cuerpo
    assert "razonamiento" in cuerpo


@pytest.mark.parametrize("name", sorted(REVISORES))
def test_hallazgo_sin_evidencia(name):
    linea = _linea_con(_cuerpo(name), "`archivo:línea`")
    assert "evidencia" in linea
    assert "no lo reportes" in linea


@pytest.mark.parametrize("name", sorted(REVISORES))
def test_criterios_del_veredicto(name):
    cuerpo = _cuerpo(name)
    criterios = cuerpo[cuerpo.index("Criterios del veredicto:") :]
    assert "`fail`" in criterios and "critical" in criterios and "medium" in criterios
    assert "`pass_with_minor`" in criterios
    assert "`pass`" in criterios
    assert "la verificación falló" in criterios


def test_qa_tests_debilitados_son_critical():
    cuerpo = _cuerpo("qa")
    linea = _linea_con(cuerpo, "`skip`")
    assert "debilit" in linea and "critical" in linea
    assert "critical" in _linea_con(cuerpo, "`live`")
    assert "## Plan de pruebas" in cuerpo
    assert "test_<escenario>" in cuerpo
    assert "tmp_path" in cuerpo and "conftest.py" in cuerpo


def test_producto_preguntas_y_trazabilidad():
    cuerpo = _cuerpo("producto")
    assert "WHEN" in cuerpo and "THEN" in cuerpo
    assert "## Preguntas y respuestas" in cuerpo
    assert "## Matriz de trazabilidad" in cuerpo
    assert "abierta: requiere al humano" in cuerpo
    assert "cubierto / parcial / no cubierto" in cuerpo
    assert "medium" in _linea_con(cuerpo, "no cubierto es")


def test_revisor_pr_ramas_de_loop_y_land():
    cuerpo = _cuerpo("revisor-pr")
    assert "factory/<run-id>" in cuerpo
    lineas = cuerpo.splitlines()
    # Solo criterios y verificación del loop, nunca el razonamiento del maker (spec team-match).
    seccion = cuerpo.split("### Ramas de loop", 1)[1].split("\n## ", 1)[0]
    permitidas = seccion.split("**No leas**", 1)[0]
    for artefacto in ("goal.md", "rounds/<n>/checks.md", "land/checks.md"):
        assert artefacto in permitidas, artefacto
    prohibicion = next(linea for linea in seccion.splitlines() if linea.startswith("**No leas**"))
    prohibidos = ("decision.md", "loop-state.md", "rounds/<n>/maker.md", "rounds/<n>/review.md")
    for artefacto in prohibidos:
        assert artefacto in prohibicion and artefacto not in permitidas, artefacto
    assert any("factory land" in linea and "decisión humana" in linea for linea in lineas)
    assert "## Resumen para el autor" in cuerpo
    assert "integrar / pedir cambios / descartar" in cuerpo


def test_revisor_pr_rango_con_tres_puntos_y_archivo_completo():
    cuerpo = _cuerpo("revisor-pr")
    assert "git diff base...rama" in cuerpo
    assert "git log base..rama" in cuerpo
    assert "merge-base" in cuerpo
    assert "Lee el archivo completo" in cuerpo
    assert "Lee la versión de la rama" in cuerpo


def test_revisor_pr_reglas_citadas():
    cuerpo = _cuerpo("revisor-pr")
    assert "AGENTS.md" in cuerpo and "CLAUDE.md" in cuerpo
    plantilla = cuerpo[cuerpo.index("- Sugerencia:") :]
    assert "- Regla:" in plantilla


def test_revisor_pr_un_solo_veredicto():
    linea = _linea_con(_cuerpo("revisor-pr"), "dos o ninguna")
    assert "`fail`" in linea


def test_revisor_pr_higiene_de_commits_del_repo():
    cuerpo = _cuerpo("revisor-pr")
    assert "conventional commits" in _linea_con(cuerpo, "Este repo")
    assert "Co-Authored-By" in cuerpo
    for resto in ("`WIP`", "`fixup!`", "`tmp`"):
        assert resto in cuerpo
    assert "formato `factory/<run-id>`" in cuerpo
    # Las instantáneas del motor no se juzgan como commits humanos.
    assert "exentos" in _linea_con(cuerpo, "promover feature <id>` y `factory: integrar")
