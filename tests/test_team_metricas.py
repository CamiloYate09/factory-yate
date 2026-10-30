"""Contrato del jugador `metricas` (#5): frontmatter D2/D8, secciones y reglas de gravedad."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
AGENTE = REPO / ".claude" / "agents" / "metricas.md"
SOLO_LECTURA = {"Read", "Grep", "Glob"}


def _frontmatter(path: Path) -> tuple[dict, str]:
    texto = path.read_text(encoding="utf-8")
    vacio, cabecera, cuerpo = texto.split("---", 2)
    assert vacio == "", "el archivo debe empezar por el frontmatter"
    return yaml.safe_load(cabecera), cuerpo


def _cuerpo() -> str:
    return _frontmatter(AGENTE)[1]


def test_frontmatter_del_jugador():
    datos, _ = _frontmatter(AGENTE)
    assert list(datos) == [
        "name",
        "description",
        "tools",
        "model",
        "dorsal",
        "tipo",
        "convocatoria",
    ]
    assert datos["name"] == AGENTE.stem == "metricas"
    assert datos["dorsal"] == 5 and type(datos["dorsal"]) is int
    assert datos["tipo"] == "revisor"
    assert datos["model"] == "sonnet"
    assert datos["convocatoria"] == "**/*.py"


def test_revisor_de_solo_lectura():
    datos, _ = _frontmatter(AGENTE)
    assert isinstance(datos["tools"], str)
    herramientas = {t.strip() for t in datos["tools"].split(",")}
    assert herramientas <= SOLO_LECTURA


def test_descripcion_en_una_linea_y_sin_truncar():
    datos, _ = _frontmatter(AGENTE)
    descripcion = datos["description"]
    assert "\n" not in descripcion
    for clave in ("métricas", "(#5)", "factory complexity", "Solo lectura"):
        assert clave in descripcion


def test_secciones_obligatorias():
    cuerpo = _cuerpo()
    for seccion in (
        "## Qué recibes",
        "## Reglas",
        "## Checklist",
        "## Formato de salida",
        "## Jugador: metricas (#5)",
        "## Veredicto",
        "## Hallazgos",
        "## Tabla de complejidad",
    ):
        assert seccion in cuerpo, seccion
    assert "central-izquierdo" in cuerpo


def test_recibe_el_informe_que_ejecuta_el_tecnico():
    cuerpo = _cuerpo()
    assert "factory complexity --base <ref> --json" in cuerpo
    recibe = cuerpo.split("## Qué recibes", 1)[1].split("## Reglas", 1)[0]
    assert "criterios" in recibe and "diff" in recibe and "factory complexity" in recibe
    assert "razonamiento" in recibe


def test_no_modifica_archivos_ni_ejecuta_comandos():
    reglas = _cuerpo().split("## Reglas", 1)[1].split("## Checklist", 1)[0]
    assert "solo lectura" in reglas
    assert "No ejecutas comandos" in reglas


def test_hallazgo_sin_ubicacion_o_evidencia_no_cuenta():
    reglas = _cuerpo().split("## Reglas", 1)[1].split("## Checklist", 1)[0]
    assert "`archivo:línea`" in reglas
    assert "no cuenta" in reglas


def test_reglas_de_gravedad():
    cuerpo = _cuerpo()
    assert re.search(r"empeorada.*rango C o inferior.*`minor`", cuerpo)
    assert re.search(r"nueva o empeorada.*rango D o superior.*`medium`", cuerpo)
    assert re.search(r"sin cambios.*nunca es un hallazgo", cuerpo)


def test_funcion_empeorada_hasta_d():
    """Escenario: una función que pasa de 18 a 23 es un hallazgo `medium`."""
    cuerpo = _cuerpo()
    ejemplo = next(linea for linea in cuerpo.splitlines() if "de 18 a 23" in linea)
    assert "`medium`" in ejemplo
    assert "D" in ejemplo


def test_informe_sin_ref_o_con_ref_y_vacio():
    """`ref` nulo = falta el informe `--base`; con `ref` y sin funciones no hay hallazgos."""
    reglas = _cuerpo().split("## Reglas", 1)[1].split("## Checklist", 1)[0]
    regla = next(linea for linea in reglas.splitlines() if "`ref`" in linea)
    assert "nulo" in regla and "como si faltara el informe" in regla
    assert "sin funciones" in regla and "no genera hallazgos de complejidad" in regla
    assert "`pass`" not in regla  # el veredicto depende también de la verificación
    assert "`ref`" in _cuerpo().split("## Reglas", 1)[0]  # la forma del JSON nombra `ref`


def test_formato_empieza_por_la_cabecera_del_jugador():
    cuerpo = _cuerpo()
    formato = cuerpo.split("## Formato de salida", 1)[1]
    bloque = formato.split("```", 2)[1]
    assert bloque.strip().startswith("## Jugador: metricas (#5)")
    assert "exactamente con la línea `## Jugador: metricas (#5)`" in formato
    assert "base → actual" in bloque


def test_propone_refactorizaciones_concretas_sin_romper_tests():
    cuerpo = _cuerpo()
    for propuesta in (
        "Extraer función",
        "Cláusulas de guarda",
        "Tabla de despacho",
        "Separar validación",
    ):
        assert propuesta in cuerpo
    assert "no debe romper tests" in cuerpo


def test_criterios_del_veredicto():
    cuerpo = _cuerpo()
    assert "`fail`: hay algún hallazgo `critical` o `medium`" in cuerpo
    assert "`pass_with_minor`: solo hay hallazgos `minor`" in cuerpo
    assert "`pass`: no hay hallazgos" in cuerpo
