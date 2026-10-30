"""Convocatoria determinista del equipo (D9): rutas cambiadas y petición → jugadores con motivo.

Un jugador queda convocado si algún glob de su `convocatoria` coincide con alguna ruta, si
declara `peticion` y hay petición, o si declara `siempre` y hay rutas o petición. El técnico no
aparece: es quien convoca, y ajusta esta sugerencia justificando cada cambio.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from factory.globs import matches
from factory.team import TeamError
from factory.team.roster import Member, Roster
from factory.util import GitError, git

MAX_RUTAS_MOTIVO = 3
MAX_RUTAS_TEXTO = 10
SIN_PARTIDO = "Sin cambios ni petición: no hay partido."


@dataclass(frozen=True)
class Convocado:
    member: Member
    motivo: str


@dataclass
class Lineup:
    base: str | None  # None si las rutas vienen de --paths
    rutas: list[str]
    peticion: bool
    convocados: list[Convocado]
    no_convocados: list[Member]
    tecnico: str | None = None

    @property
    def hay_partido(self) -> bool:
        return bool(self.rutas) or self.peticion

    def to_dict(self) -> dict:
        return {
            "base": self.base,
            "rutas": list(self.rutas),
            "peticion": self.peticion,
            "convocados": [
                {
                    "name": c.member.name,
                    "dorsal": c.member.dorsal,
                    "posicion": c.member.posicion,
                    "tipo": c.member.tipo,
                    "motivo": c.motivo,
                }
                for c in self.convocados
            ],
            "no_convocados": [
                {"name": m.name, "dorsal": m.dorsal, "posicion": m.posicion}
                for m in self.no_convocados
            ],
        }


def _git(root: Path, *args: str, strip: bool = True) -> str:
    try:
        return git(root, *args, strip=strip)
    except OSError as exc:
        raise TeamError(f"no se puede ejecutar git ({exc}); indica las rutas con --paths") from exc
    except UnicodeDecodeError as exc:
        raise TeamError(
            "git devolvió rutas que no son UTF-8: indica las rutas cambiadas con --paths"
        ) from exc


def _nul_list(output: str) -> list[str]:
    return [item for item in output.split("\0") if item]


def changed_paths(root: Path, base: str = "HEAD") -> list[str]:
    """`git diff --name-only <base>` más los archivos no versionados, sin repetir y ordenados."""
    if not base or base.startswith("-"):
        raise TeamError(f"referencia git no válida: {base!r}")
    not_a_repo = f"{root} no es un repositorio git: indica las rutas cambiadas con --paths"
    try:
        inside = _git(root, "rev-parse", "--is-inside-work-tree")
    except GitError as exc:
        raise TeamError(not_a_repo) from exc
    if inside != "true":  # p. ej. un repo bare o el propio directorio .git
        raise TeamError(not_a_repo)
    try:
        _git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    except GitError as exc:
        if base == "HEAD":
            raise TeamError(
                "el repositorio aún no tiene commits: haz el primer commit o indica las rutas "
                "cambiadas con --paths"
            ) from exc
        raise TeamError(
            f"referencia git no válida: «{base}» (¿existe la rama o el commit? usa --base REF "
            "o --paths)"
        ) from exc
    try:
        # --no-renames: un renombrado aporta el origen y el destino a la convocatoria.
        diff = _git(
            root, "diff", "--name-only", "--no-renames", "-z", "--relative", base, "--", strip=False
        )
        others = _git(root, "ls-files", "-z", "--others", "--exclude-standard", strip=False)
    except GitError as exc:
        raise TeamError(str(exc)) from exc
    return sorted(set(_nul_list(diff)) | set(_nul_list(others)))


def normalize_paths(paths: list[str]) -> list[str]:
    """Rutas de --paths tal cual, sin `./` inicial, vacías ni repetidas."""
    out: list[str] = []
    for path in paths:
        path = path.strip().removeprefix("./")
        if path and path not in out:
            out.append(path)
    return out


def load_peticion(text: str | None, file: str | None) -> str | None:
    """Texto de la petición (`--peticion` o `--peticion-file`), o None si no hay petición."""
    if file is not None:
        try:
            text = Path(file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise TeamError(f"no se puede leer la petición {file}: {exc}") from exc
    return text if text and text.strip() else None


def motivo(member: Member, rutas: list[str], peticion: bool) -> str:
    """Motivo de la convocatoria (vacío si no se convoca): hasta 3 rutas o el token."""
    reasons = []
    patterns = member.globs
    hits = [ruta for ruta in rutas if matches(ruta, patterns)] if patterns else []
    if hits:
        extra = len(hits) - MAX_RUTAS_MOTIVO
        reasons.append(
            "rutas: "
            + ", ".join(hits[:MAX_RUTAS_MOTIVO])
            + (f" (+{extra} más)" if extra > 0 else "")
        )
    if peticion and "peticion" in member.convocatoria:
        reasons.append("peticion")
    if (rutas or peticion) and "siempre" in member.convocatoria:
        reasons.append("siempre")
    return "; ".join(reasons)


def convocar(roster: Roster, rutas: list[str], peticion: bool, base: str | None) -> Lineup:
    convocados, no_convocados = [], []
    for member in roster.jugadores:
        why = motivo(member, rutas, peticion)
        if why:
            convocados.append(Convocado(member, why))
        else:
            no_convocados.append(member)
    tecnico = roster.tecnico.name if roster.tecnico else None
    return Lineup(base, list(rutas), peticion, convocados, no_convocados, tecnico)


def render(lineup: Lineup) -> str:
    if not lineup.hay_partido:
        return SIN_PARTIDO
    origen = f"frente a {lineup.base}" if lineup.base else "indicadas con --paths"
    shown = ", ".join(lineup.rutas[:MAX_RUTAS_TEXTO])
    extra = len(lineup.rutas) - MAX_RUTAS_TEXTO
    out = [
        "Convocatoria sugerida",
        f"Rutas ({len(lineup.rutas)}, {origen}): "
        + (shown + (f" (+{extra} más)" if extra > 0 else "") if lineup.rutas else "ninguna"),
        f"Petición: {'sí' if lineup.peticion else 'no'}",
        f"Técnico: {lineup.tecnico or 'sin técnico'} (convoca y ajusta la sugerencia)",
        "",
        f"Convocados ({len(lineup.convocados)}):",
    ]
    out += [
        f"  #{c.member.dorsal:<3}{c.member.posicion:<19}{c.member.name} ({c.member.tipo}) "
        f"— {c.motivo}"
        for c in lineup.convocados
    ] or ["  nadie"]
    out.append(f"No convocados ({len(lineup.no_convocados)}):")
    out += [f"  #{m.dorsal:<3}{m.posicion:<19}{m.name}" for m in lineup.no_convocados] or [
        "  nadie"
    ]
    return "\n".join(out)
