"""Plantilla del equipo: lectura y validación del frontmatter de `.claude/agents/*.md` (D1, D8).

Un agente es miembro del equipo si su frontmatter declara `tipo` o `dorsal`; el resto (como el
`checker`, que actúa de árbitro) queda fuera y no se valida. La validación nunca lanza
excepciones: devuelve una línea `"<archivo>: <motivo>"` por error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

AGENTS_DIR = Path(".claude") / "agents"
ARBITRO = "checker"
TIPOS = ("revisor", "constructor", "tecnico")
TOKENS = ("siempre", "peticion")
POSICIONES = {
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
LINEAS = (
    ("portero", (1,)),
    ("defensa", (2, 4, 5, 3)),
    ("medio", (8, 6, 10)),
    ("ataque", (7, 9, 11)),
)
SOLO_LECTURA = ("Read", "Grep", "Glob")
EDICION = ("Edit", "MultiEdit", "Write", "NotebookEdit")
DELEGACION = ("Agent", "Task")  # `Task` es el nombre antiguo de la herramienta `Agent`


@dataclass(frozen=True)
class Member:
    """Miembro válido del equipo, declarado en `.claude/agents/<name>.md`."""

    file: str  # ruta relativa al repo, p. ej. `.claude/agents/qa.md`
    name: str
    tipo: str
    dorsal: int | None = None
    model: str | None = None
    tools: tuple[str, ...] = ()
    convocatoria: tuple[str, ...] = ()

    @property
    def posicion(self) -> str | None:
        return POSICIONES.get(self.dorsal) if self.dorsal is not None else None

    @property
    def globs(self) -> list[str]:
        """Elementos de la convocatoria que son globs de ruta (sin los tokens)."""
        return [item for item in self.convocatoria if item not in TOKENS]


@dataclass
class Roster:
    members: list[Member]  # solo los miembros sin errores
    errors: list[str]
    arbitro: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def tecnico(self) -> Member | None:
        return next((m for m in self.members if m.tipo == "tecnico"), None)

    @property
    def jugadores(self) -> list[Member]:
        """Jugadores válidos (todo miembro salvo el técnico), por dorsal."""
        players = [m for m in self.members if m.tipo != "tecnico" and m.dorsal is not None]
        return sorted(players, key=lambda m: m.dorsal or 0)

    def por_dorsal(self) -> dict[int, Member]:
        return {m.dorsal: m for m in self.jugadores if m.dorsal is not None}

    def vacantes(self) -> list[int]:
        ocupados = self.por_dorsal()
        return [d for d in POSICIONES if d not in ocupados]

    def to_dict(self) -> dict:
        return {
            "tecnico": self.tecnico.name if self.tecnico else None,
            "arbitro": self.arbitro,
            "jugadores": [
                {
                    "dorsal": m.dorsal,
                    "posicion": m.posicion,
                    "name": m.name,
                    "tipo": m.tipo,
                    "model": m.model,
                    "convocatoria": list(m.convocatoria),
                }
                for m in self.jugadores
            ],
            "vacantes": [{"dorsal": d, "posicion": POSICIONES[d]} for d in self.vacantes()],
        }


def _yaml_reason(exc: yaml.YAMLError) -> str:
    problem = getattr(exc, "problem", None)
    mark = getattr(exc, "problem_mark", None)
    if problem and mark is not None:
        return f"{problem} (línea {mark.line + 2})"  # +2: la línea 1 es el `---` de apertura
    return str(exc).splitlines()[0] if str(exc) else type(exc).__name__


def read_frontmatter(text: str) -> dict | None:
    """Frontmatter YAML entre la primera pareja de líneas `---`, o None si el archivo no
    empieza por `---`. Lanza ValueError si está sin cerrar, es ilegible o no es un dict."""
    lines = text.removeprefix("﻿").splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    end = next((i for i, line in enumerate(lines[1:], 1) if line.rstrip() == "---"), None)
    if end is None:
        raise ValueError("frontmatter ilegible: falta la línea `---` de cierre")
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter ilegible: {_yaml_reason(exc)}") from exc
    if not isinstance(meta, dict):
        raise ValueError("frontmatter ilegible: no es un diccionario de claves")
    return meta


def as_list(value: object, key: str) -> tuple[str, ...] | None:
    """Normaliza una cadena separada por comas o una lista YAML de cadenas (None si falta)."""
    if value is None:
        return None
    if isinstance(value, str):
        items: list[str] = value.split(",")
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        items = value
    else:
        raise ValueError(f"`{key}` debe ser una cadena separada por comas o una lista de cadenas")
    return tuple(item.strip() for item in items if item.strip())


def _tool_name(tool: str) -> str:
    """`Bash(git diff:*)` → `Bash`."""
    return tool.split("(", 1)[0].strip()


def _dorsal_errors(meta: dict) -> tuple[int | None, list[str]]:
    if "dorsal" not in meta or meta["dorsal"] is None:
        return None, ["falta `dorsal`: un jugador lleva un dorsal entre 1 y 11"]
    dorsal = meta["dorsal"]
    if isinstance(dorsal, bool) or not isinstance(dorsal, int):
        return None, [f"el dorsal {dorsal!r} no es válido: debe ser un entero entre 1 y 11"]
    if dorsal not in POSICIONES:
        return None, [f"dorsal {dorsal} fuera de rango: debe estar entre 1 y 11"]
    return dorsal, []


def _permission_errors(tipo: str, tools: tuple[str, ...]) -> list[str]:
    names = [_tool_name(t) for t in tools]
    if tipo == "revisor":
        if not tools:
            return [
                "un revisor es de solo lectura: declara `tools: Read, Grep, Glob` "
                "(sin `tools` hereda todas las herramientas)"
            ]
        extra = [t for t, n in zip(tools, names, strict=True) if n not in SOLO_LECTURA]
        if extra:
            return [
                "un revisor es de solo lectura: solo admite Read, Grep y Glob "
                f"(sobra: {', '.join(extra)})"
            ]
    elif tipo == "constructor":
        if not tools:
            return [
                "un constructor no convoca a otros agentes: declara `tools` sin Agent "
                "(sin `tools` hereda todas las herramientas, Agent incluida)"
            ]
        if any(n in DELEGACION for n in names):
            return ["un constructor no convoca a otros agentes: quita Agent de `tools`"]
    elif tipo == "tecnico":
        if not tools:
            return [
                "el técnico no edita archivos: declara `tools` sin Edit, Write ni NotebookEdit "
                "(sin `tools` hereda todas las herramientas)"
            ]
        edit = [t for t, n in zip(tools, names, strict=True) if n in EDICION]
        if edit:
            return [f"el técnico no edita archivos: quita {', '.join(edit)} de `tools`"]
    return []


def _check_member(label: str, stem: str, meta: dict) -> tuple[Member | None, int | None, list[str]]:
    """Valida un miembro aislado. Devuelve el miembro (si no hay errores), su dorsal (si es
    válido, para detectar repetidos aunque haya otros errores) y los motivos de error."""
    errors: list[str] = []
    name = meta.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"falta `name`: debe ser «{stem}», como el nombre del archivo")
    elif name != stem:
        errors.append(f"`name` «{name}» no coincide con el nombre del archivo («{stem}»)")
    tipo = meta.get("tipo")
    if tipo not in TIPOS:
        errors.append(f"`tipo` {tipo!r} no es válido: usa revisor, constructor o tecnico")
    tools: tuple[str, ...] | None = ()
    convocatoria: tuple[str, ...] = ()
    try:
        tools = as_list(meta.get("tools"), "tools") or ()
    except ValueError as exc:
        tools = None  # tipo incorrecto: no se pueden comprobar los permisos
        errors.append(str(exc))
    try:
        convocatoria = as_list(meta.get("convocatoria"), "convocatoria") or ()
    except ValueError as exc:
        errors.append(str(exc))
    dorsal = None
    if tipo == "tecnico":
        if meta.get("dorsal") is not None:
            errors.append("el técnico no lleva dorsal: quita `dorsal`")
    else:
        dorsal, dorsal_errors = _dorsal_errors(meta)
        errors += dorsal_errors
    if tipo in TIPOS and tools is not None:
        errors += _permission_errors(str(tipo), tools)
    if errors or tools is None:
        return None, dorsal, errors
    model = meta.get("model")
    member = Member(
        file=label,
        name=str(name),
        tipo=str(tipo),
        dorsal=dorsal,
        model=None if model is None else str(model),
        tools=tools,
        convocatoria=convocatoria,
    )
    return member, dorsal, []


def load_roster(root: Path) -> Roster:
    """Lee `.claude/agents/*.md` en orden y valida la plantilla (D1, D8). Sin directorio o sin
    miembros, la plantilla está vacía y es válida."""
    directory = root / AGENTS_DIR
    members: list[Member] = []
    errors: list[str] = []
    team_files: set[str] = set()
    dorsales: dict[int, str] = {}
    tecnico: str | None = None
    try:
        paths = sorted(p for p in directory.glob("*.md") if p.is_file())
    except OSError as exc:
        return Roster([], [f"{AGENTS_DIR.as_posix()}: no se puede leer ({exc})"])
    for path in paths:
        label = (AGENTS_DIR / path.name).as_posix()
        try:
            meta = read_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{label}: {exc}")
            team_files.add(label)
            continue
        if meta is None or ("tipo" not in meta and "dorsal" not in meta):
            continue
        team_files.add(label)
        member, dorsal, reasons = _check_member(label, path.stem, meta)
        if dorsal is not None:
            if dorsal in dorsales:
                reasons.append(f"dorsal {dorsal} repetido: ya lo lleva {dorsales[dorsal]}")
            else:
                dorsales[dorsal] = label
        if meta.get("tipo") == "tecnico":
            if tecnico is not None:
                reasons.append(f"más de un técnico: ya lo es {tecnico}")
            else:
                tecnico = label
        if reasons:
            errors.extend(f"{label}: {reason}" for reason in reasons)
            continue
        if member is not None:
            members.append(member)
    arbitro_file = (AGENTS_DIR / f"{ARBITRO}.md").as_posix()
    arbitro = (
        ARBITRO if (root / arbitro_file).is_file() and arbitro_file not in team_files else None
    )
    return Roster(members, errors, arbitro)


def _member_label(member: Member) -> str:
    extra = ", ".join(x for x in (member.tipo, member.model) if x)
    return f"{member.name} ({extra})"


def render(roster: Roster) -> str:
    """Formación 4-3-3 por líneas, con técnico, árbitro y vacantes."""
    por_dorsal = roster.por_dorsal()
    tecnico = roster.tecnico
    out = [
        "Formación 4-3-3",
        f"Técnico: {_member_label(tecnico) if tecnico else 'sin técnico'}",
        f"Árbitro: {roster.arbitro or 'sin árbitro'}",
    ]
    for linea, dorsales in LINEAS:
        out.append(f"\n{linea.capitalize()}")
        for dorsal in dorsales:
            member = por_dorsal.get(dorsal)
            who = _member_label(member) if member else "vacante"
            out.append(f"  #{dorsal:<3}{POSICIONES[dorsal]:<19}{who}")
    vacantes = roster.vacantes()
    out.append(
        f"\n{len(por_dorsal)} jugador(es); vacantes: {', '.join(map(str, vacantes)) or 'ninguna'}"
    )
    return "\n".join(out)
