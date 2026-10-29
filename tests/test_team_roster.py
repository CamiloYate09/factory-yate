"""Escenarios de `team-roster`: plantilla, validación, formación y doctor (`factory team`)."""

import json
from pathlib import Path

from conftest import make_harness

from factory.cli import main
from factory.team.roster import POSICIONES, load_roster, read_frontmatter

CHECKER = """---
name: checker
description: Revisor independiente y de solo lectura.
tools: Read, Grep, Glob
model: opus
---

Eres el Checker.
"""

# Plantilla inicial de D2: (name, dorsal, tipo, model, tools, convocatoria).
D2 = [
    (
        "seguridad",
        1,
        "revisor",
        "opus",
        "Read, Grep, Glob",
        "**/*.py, **/*.sh, pyproject.toml, factory.toml, prompts/**, .claude/**, "
        "src/factory/templates/**, goals/**",
    ),
    ("qa", 2, "revisor", "sonnet", "Read, Grep, Glob", "src/**, tests/**"),
    (
        "documentador",
        3,
        "constructor",
        "sonnet",
        "Read, Grep, Glob, Edit, Write",
        "src/factory/cli.py, src/factory/config.py, factory.toml, docs/**, README.md, "
        "AGENTS.md, CLAUDE.md",
    ),
    ("revisor-pr", 4, "revisor", "opus", "Read, Grep, Glob", "siempre"),
    ("metricas", 5, "revisor", "sonnet", "Read, Grep, Glob", "**/*.py"),
    ("producto", 6, "revisor", "opus", "Read, Grep, Glob", "peticion, openspec/changes/**"),
    (
        "ingeniero-software",
        9,
        "constructor",
        "sonnet",
        "Read, Grep, Glob, Edit, Write, Bash",
        "peticion",
    ),
]


def agent_text(
    name: str,
    *,
    tipo: str | None = None,
    dorsal: object = None,
    tools: str | None = "Read, Grep, Glob",
    model: str | None = "sonnet",
    convocatoria: str | None = None,
    extra: str = "",
) -> str:
    """Agente con el frontmatter de referencia de D8."""
    lines = ["---", f"name: {name}", f"description: Agente {name} de prueba."]
    if tools is not None:
        lines.append(f"tools: {tools}")
    if model is not None:
        lines.append(f"model: {model}")
    if dorsal is not None:
        lines.append(f"dorsal: {dorsal}")
    if tipo is not None:
        lines.append(f"tipo: {tipo}")
    if convocatoria is not None:
        lines.append(f'convocatoria: "{convocatoria}"')
    if extra:
        lines.append(extra)
    lines += ["---", "", f"Cuerpo de {name}, en español.", ""]
    return "\n".join(lines)


def write_agent(root: Path, name: str, text: str | None = None, **fields) -> Path:
    path = root / ".claude" / "agents" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text is not None else agent_text(name, **fields), encoding="utf-8")
    return path


def write_tecnico(root: Path, tools: str | None = "Agent, Read, Grep, Glob, Bash", **fields):
    return write_agent(root, "tecnico", tipo="tecnico", tools=tools, model="opus", **fields)


def write_d2(root: Path, checker: bool = True) -> Path:
    """Plantilla inicial completa de D2 (técnico, 7 jugadores) y, opcionalmente, el árbitro."""
    write_tecnico(root)
    for name, dorsal, tipo, model, tools, convocatoria in D2:
        write_agent(
            root,
            name,
            tipo=tipo,
            dorsal=dorsal,
            model=model,
            tools=tools,
            convocatoria=convocatoria,
        )
    if checker:
        write_agent(root, "checker", CHECKER)
    return root


def _team(root: Path, *args: str) -> int:
    return main(["--root", str(root), "team", *args])


# ----------------------------------------------------------------------- Miembros del equipo


def test_jugador_declarado(tmp_path):
    write_agent(tmp_path, "qa", tipo="revisor", dorsal=2, convocatoria="src/**, tests/**")
    roster = load_roster(tmp_path)
    assert roster.errors == []
    [qa] = roster.members
    assert (qa.name, qa.tipo, qa.dorsal) == ("qa", "revisor", 2)
    assert qa.convocatoria == ("src/**", "tests/**")
    assert qa.tools == ("Read", "Grep", "Glob")
    assert qa.file == ".claude/agents/qa.md"


def test_agente_ajeno_al_equipo(tmp_path, capsys):
    write_agent(tmp_path, "checker", CHECKER)
    roster = load_roster(tmp_path)
    assert roster.members == [] and roster.errors == []
    assert _team(tmp_path, "validate") == 0
    assert "✗" not in capsys.readouterr().out


def test_archivo_sin_frontmatter_queda_fuera_sin_error(tmp_path):
    write_agent(tmp_path, "LEEME", "# Agentes\n\n---\nnotas: sueltas\n---\n")
    assert load_roster(tmp_path).errors == []


# ------------------------------------------------------------------------ Posición por dorsal


def test_posicion_del_dorsal_2(tmp_path):
    write_agent(tmp_path, "qa", tipo="revisor", dorsal=2, convocatoria="src/**")
    [qa] = load_roster(tmp_path).members
    assert qa.posicion == "lateral-derecho"


def test_formacion_433_completa():
    assert POSICIONES == {
        1: "portero",
        2: "lateral-derecho",
        3: "lateral-izquierdo",
        4: "central-derecho",
        5: "central-izquierdo",
        6: "pivote",
        7: "extremo-derecho",
        8: "interior-derecho",
        9: "delantero-centro",
        10: "mediapunta",
        11: "extremo-izquierdo",
    }


# -------------------------------------------------------------------- Validación de la plantilla


def test_plantilla_valida(tmp_path, capsys):
    write_d2(tmp_path)
    assert _team(tmp_path, "validate") == 0
    assert "Plantilla válida: 8 miembro(s)" in capsys.readouterr().out
    assert _team(tmp_path, "validate", "--json") == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "errores": []}


def test_sin_equipo(tmp_path, capsys):
    assert _team(tmp_path, "validate") == 0  # sin .claude/agents/
    write_agent(tmp_path, "checker", CHECKER)  # solo el árbitro: ningún miembro
    capsys.readouterr()
    assert _team(tmp_path, "validate", "--json") == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "errores": []}
    assert _team(tmp_path, "list", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["arbitro"] == "checker" and data["tecnico"] is None
    assert data["jugadores"] == [] and len(data["vacantes"]) == 11


# ------------------------------------------------------------------- Identidad y dorsal válidos


def test_dorsal_repetido(tmp_path, capsys):
    write_agent(tmp_path, "revisor-pr", tipo="revisor", dorsal=4, convocatoria="siempre")
    write_agent(tmp_path, "zaguero", tipo="revisor", dorsal=4, convocatoria="src/**")
    assert _team(tmp_path, "validate") == 1
    out = capsys.readouterr().out
    [line] = [x for x in out.splitlines() if x.startswith("✗")]
    assert ".claude/agents/zaguero.md" in line and ".claude/agents/revisor-pr.md" in line
    assert "dorsal 4 repetido" in line


def test_dorsal_repetido_el_primero_conserva_el_puesto(tmp_path, capsys):
    write_agent(tmp_path, "revisor-pr", tipo="revisor", dorsal=4, convocatoria="siempre")
    write_agent(tmp_path, "zaguero", tipo="revisor", dorsal=4, convocatoria="src/**")
    assert _team(tmp_path, "list", "--json") == 0
    captured = capsys.readouterr()
    assert "dorsal 4 repetido" in captured.err
    data = json.loads(captured.out)
    assert [j["name"] for j in data["jugadores"]] == ["revisor-pr"]


def test_un_archivo_invalido_no_desplaza_a_uno_valido(tmp_path):
    write_agent(tmp_path, "a", tipo="revisor", dorsal=4, tools="Read, Edit", convocatoria="x")
    write_agent(tmp_path, "b", tipo="revisor", dorsal=4, convocatoria="src/**")
    write_agent(tmp_path, "entrenador", tipo="tecnico", tools="Agent, Write", model="opus")
    write_tecnico(tmp_path)
    roster = load_roster(tmp_path)
    assert [m.name for m in roster.members] == ["b", "tecnico"]
    assert roster.tecnico is not None and roster.tecnico.name == "tecnico"
    assert roster.errors == [
        ".claude/agents/a.md: un revisor es de solo lectura: solo admite Read, Grep y Glob "
        "(sobra: Edit)",
        ".claude/agents/a.md: dorsal 4 repetido: ya lo lleva .claude/agents/b.md",
        ".claude/agents/entrenador.md: el técnico no edita archivos: quita Write de `tools`",
        ".claude/agents/entrenador.md: más de un técnico: ya lo es .claude/agents/tecnico.md",
    ]


def test_dorsal_fuera_de_rango(tmp_path, capsys):
    write_agent(tmp_path, "suplente", tipo="revisor", dorsal=12, convocatoria="src/**")
    assert _team(tmp_path, "validate") == 1
    out = capsys.readouterr().out
    assert ".claude/agents/suplente.md: " in out
    assert "debe estar entre 1 y 11" in out


def test_dorsal_que_no_es_entero(tmp_path):
    write_agent(tmp_path, "a", tipo="revisor", dorsal="true", convocatoria="src/**")
    write_agent(tmp_path, "b", tipo="revisor", dorsal='"2"', convocatoria="src/**")
    write_agent(tmp_path, "c", tipo="revisor", dorsal="2.0", convocatoria="src/**")
    errors = load_roster(tmp_path).errors
    assert len(errors) == 3
    assert all("debe ser un entero entre 1 y 11" in e for e in errors)


def test_jugador_sin_dorsal(tmp_path):
    write_agent(tmp_path, "qa", tipo="revisor", convocatoria="src/**")
    [error] = load_roster(tmp_path).errors
    assert error.startswith(".claude/agents/qa.md: falta `dorsal`")


def test_agente_con_dorsal_y_sin_tipo(tmp_path):
    write_agent(tmp_path, "qa", dorsal=2, convocatoria="src/**")
    [error] = load_roster(tmp_path).errors
    assert "`tipo`" in error and "revisor, constructor o tecnico" in error


def test_tipo_desconocido(tmp_path):
    write_agent(tmp_path, "qa", tipo="delantero", dorsal=2, convocatoria="src/**")
    [error] = load_roster(tmp_path).errors
    assert error.startswith(".claude/agents/qa.md: `tipo` 'delantero' no es válido")


def test_name_distinto_del_archivo(tmp_path):
    text = agent_text("otro", tipo="revisor", dorsal=2, convocatoria="src/**")
    write_agent(tmp_path, "qa", text)
    [error] = load_roster(tmp_path).errors
    assert error == (
        ".claude/agents/qa.md: `name` «otro» no coincide con el nombre del archivo («qa»)"
    )


def test_frontmatter_ilegible(tmp_path):
    write_agent(tmp_path, "roto", "---\nname: roto\ntipo: [revisor\n---\n")
    write_agent(tmp_path, "dos-puntos", "---\nname: x\ndescription: a: b\ndorsal: 2\n---\n")
    write_agent(tmp_path, "abierto", "---\nname: abierto\ntipo: revisor\n")
    write_agent(tmp_path, "fecha", "---\nname: fecha\ntipo: revisor\nalta: 2026-13-45\n---\n")
    errors = load_roster(tmp_path).errors
    assert len(errors) == 4
    assert all("frontmatter ilegible" in e for e in errors)
    assert {e.split(":")[0] for e in errors} == {
        ".claude/agents/roto.md",
        ".claude/agents/dos-puntos.md",
        ".claude/agents/abierto.md",
        ".claude/agents/fecha.md",
    }


def test_frontmatter_ilegible_fuera_del_equipo_no_es_error(tmp_path, capsys):
    # Agente al estilo de Claude Code con `: ` en la descripción (YAML estricto lo rechaza).
    write_agent(tmp_path, "ajeno", "---\nname: ajeno\ndescription: Úsalo así: <example>\n---\n")
    write_agent(tmp_path, "LEEME", "---\n\nNotas sueltas sobre los agentes.\n")  # sin cierre
    write_agent(tmp_path, "vacio", "---\n---\n")
    write_agent(tmp_path, "lista", "---\n- tipo\n- dorsal\n---\n")
    assert load_roster(tmp_path).errors == []
    assert _team(tmp_path, "validate") == 0
    root = make_harness(tmp_path)
    assert main(["--root", str(root), "doctor"]) == 0
    assert "[PASS] [CRITICAL] La plantilla del equipo" in capsys.readouterr().out


def test_frontmatter_ilegible_no_lanza_en_lecturas():
    assert read_frontmatter("sin frontmatter\n") is None
    assert read_frontmatter("---\nname: x\ntipo: revisor\n---\ncuerpo") == {
        "name": "x",
        "tipo": "revisor",
    }


def test_name_que_no_es_cadena(tmp_path):
    text = "---\nname: 5\ntools: Read\ntipo: revisor\ndorsal: 2\nconvocatoria: x\n---\n"
    write_agent(tmp_path, "c", text)
    [error] = load_roster(tmp_path).errors
    assert error.startswith(".claude/agents/c.md: `name` debe ser una cadena")


def test_jugador_sin_convocatoria(tmp_path):
    write_agent(tmp_path, "qa", tipo="revisor", dorsal=2)
    [error] = load_roster(tmp_path).errors
    assert error.startswith(".claude/agents/qa.md: falta `convocatoria`")


# ------------------------------------------------------------------------ Permisos según el tipo


def test_revisor_con_permisos_de_escritura(tmp_path, capsys):
    write_agent(
        tmp_path, "qa", tipo="revisor", dorsal=2, tools="Read, Grep, Glob, Edit", convocatoria="x"
    )
    assert _team(tmp_path, "validate") == 1
    out = capsys.readouterr().out
    assert ".claude/agents/qa.md: un revisor es de solo lectura" in out
    assert "Edit" in out


def test_revisor_sin_tools_hereda_todas(tmp_path):
    write_agent(tmp_path, "qa", tipo="revisor", dorsal=2, tools=None, convocatoria="src/**")
    [error] = load_roster(tmp_path).errors
    assert "un revisor es de solo lectura" in error and "hereda todas" in error


def test_tecnico_que_edita(tmp_path, capsys):
    write_tecnico(tmp_path, tools="Agent, Read, Grep, Glob, Bash, Write")
    assert _team(tmp_path, "validate") == 1
    out = capsys.readouterr().out
    assert ".claude/agents/tecnico.md: el técnico no edita archivos" in out
    assert "Write" in out


def test_tecnico_sin_tools_hereda_todas(tmp_path):
    write_tecnico(tmp_path, tools=None)
    [error] = load_roster(tmp_path).errors
    assert "el técnico no edita archivos" in error and "hereda todas" in error


def test_tecnico_con_dorsal(tmp_path):
    write_tecnico(tmp_path, dorsal=1)
    [error] = load_roster(tmp_path).errors
    assert error == ".claude/agents/tecnico.md: el técnico no lleva dorsal: quita `dorsal`"


def test_mas_de_un_tecnico(tmp_path):
    write_tecnico(tmp_path)
    write_agent(tmp_path, "segundo", tipo="tecnico", tools="Agent, Read", model="opus")
    [error] = load_roster(tmp_path).errors
    assert error.startswith(".claude/agents/tecnico.md: más de un técnico")
    assert ".claude/agents/segundo.md" in error


def test_constructor_que_convoca(tmp_path):
    write_agent(
        tmp_path,
        "ingeniero-software",
        tipo="constructor",
        dorsal=9,
        tools="Read, Edit, Write, Agent",
        convocatoria="peticion",
    )
    [error] = load_roster(tmp_path).errors
    assert "un constructor no convoca a otros agentes" in error


def test_formas_equivalentes_en_lista_yaml(tmp_path):
    extra = "convocatoria:\n  - src/**\n  - ' tests/** '\n  - ''"
    text = agent_text("qa", tipo="revisor", dorsal=2, tools=None, extra=extra).replace(
        "model: sonnet", "model: sonnet\ntools:\n  - Read\n  - Grep"
    )
    write_agent(tmp_path, "qa", text)
    roster = load_roster(tmp_path)
    assert roster.errors == []
    [qa] = roster.members
    assert qa.tools == ("Read", "Grep")
    assert qa.convocatoria == ("src/**", "tests/**")


def test_tools_con_tipo_incorrecto(tmp_path):
    write_agent(tmp_path, "qa", tipo="revisor", dorsal=2, tools="{a: 1}", convocatoria="src/**")
    [error] = load_roster(tmp_path).errors
    assert "`tools` debe ser una cadena separada por comas o una lista" in error


# ----------------------------------------------------------------------- Formación con vacantes


def test_plantilla_incompleta(tmp_path, capsys):
    write_d2(tmp_path)
    assert _team(tmp_path, "list") == 0
    out = capsys.readouterr().out
    assert "Técnico: tecnico (tecnico, opus)" in out
    assert "Árbitro: checker" in out
    for linea in ("Portero", "Defensa", "Medio", "Ataque"):
        assert linea in out
    for name, dorsal, *_ in D2:
        assert f"#{dorsal:<3}{POSICIONES[dorsal]:<19}{name} (" in out
    for dorsal in (7, 8, 10, 11):
        assert f"#{dorsal:<3}{POSICIONES[dorsal]:<19}vacante" in out
    assert "vacantes: 7, 8, 10, 11" in out
    # Orden de las líneas: portero, defensa (2, 4, 5, 3), medio (8, 6, 10), ataque (7, 9, 11).
    orden = [int(line.split()[0][1:]) for line in out.splitlines() if line.startswith("  #")]
    assert orden == [1, 2, 4, 5, 3, 8, 6, 10, 7, 9, 11]

    assert _team(tmp_path, "list", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tecnico"] == "tecnico" and data["arbitro"] == "checker"
    assert [j["dorsal"] for j in data["jugadores"]] == [1, 2, 3, 4, 5, 6, 9]
    assert data["vacantes"] == [
        {"dorsal": 7, "posicion": "extremo-derecho"},
        {"dorsal": 8, "posicion": "interior-derecho"},
        {"dorsal": 10, "posicion": "mediapunta"},
        {"dorsal": 11, "posicion": "extremo-izquierdo"},
    ]
    qa = next(j for j in data["jugadores"] if j["name"] == "qa")
    assert qa == {
        "dorsal": 2,
        "posicion": "lateral-derecho",
        "name": "qa",
        "tipo": "revisor",
        "model": "sonnet",
        "convocatoria": ["src/**", "tests/**"],
    }


def test_list_con_errores_sigue_con_los_validos(tmp_path, capsys):
    write_d2(tmp_path)
    write_agent(tmp_path, "qa", tipo="revisor", dorsal=2, tools="Read, Edit", convocatoria="x")
    assert _team(tmp_path, "list") == 0
    captured = capsys.readouterr()
    assert ".claude/agents/qa.md: un revisor es de solo lectura" in captured.err
    assert f"#2  {'lateral-derecho':<19}vacante" in captured.out
    assert "seguridad (revisor, opus)" in captured.out


# --------------------------------------------------------------------- Doctor valida la plantilla


def test_plantilla_rota_en_el_doctor(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    write_agent(
        root, "qa", tipo="revisor", dorsal=2, tools="Read, Grep, Glob, Edit", convocatoria="x"
    )
    assert main(["--root", str(root), "doctor"]) != 0
    out = capsys.readouterr().out
    assert "[FAIL] [CRITICAL] La plantilla del equipo (.claude/agents/) es válida" in out
    assert "factory team validate" in out
    assert ".claude/agents/qa.md: un revisor es de solo lectura" in out

    assert main(["--root", str(root), "doctor", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    check = next(c for c in data["checks"] if c["id"] == "team-roster")
    assert check["subsystem"] == "instrucciones" and check["severity"] == "critical"
    assert check["passed"] is False
    assert check["detail"].startswith(".claude/agents/qa.md: un revisor es de solo lectura")
    assert check["fix"] == "Corrige .claude/agents/qa.md y comprueba con `factory team validate`"


def test_doctor_muestra_el_primer_error_una_vez_y_cuenta_el_resto(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    write_agent(
        root, "qa", tipo="revisor", dorsal=2, tools="Read, Grep, Glob, Edit", convocatoria="x"
    )
    write_agent(root, "otro", tipo="revisor", dorsal=12, tools="Read", convocatoria="x")
    assert main(["--root", str(root), "doctor", "--json"]) == 1
    check = next(
        c for c in json.loads(capsys.readouterr().out)["checks"] if c["id"] == "team-roster"
    )
    assert check["fix"].startswith("Corrige .claude/agents/")
    assert check["fix"].endswith("(y 1 error(es) más)")
    assert main(["--root", str(root), "doctor"]) != 0
    assert capsys.readouterr().out.count(check["detail"]) == 1


def test_doctor_pasa_sin_agentes_y_con_la_plantilla_d2(tmp_path, capsys):
    root = make_harness(tmp_path / "repo")
    assert main(["--root", str(root), "doctor", "--json"]) == 0
    check = next(
        c for c in json.loads(capsys.readouterr().out)["checks"] if c["id"] == "team-roster"
    )
    assert check["passed"] is True and check["fix"] == "factory team validate"
    write_d2(root)
    assert main(["--root", str(root), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "[PASS] [CRITICAL] La plantilla del equipo (.claude/agents/) es válida" in out
    assert "instrucciones (100%)" in out
