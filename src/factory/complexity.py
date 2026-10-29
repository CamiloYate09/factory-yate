"""Complejidad ciclomática por función (D6): cálculo con `ast`, rangos A–F y delta frente a REF.

Reglas de la cuenta: base 1, y +1 por cada `if`/`elif`, `for`/`async for`, `while`, `except`,
`case` de un `match`, expresión condicional, cada `for` e `if` de una comprensión y cada
operando adicional de `and`/`or`. Las funciones anidadas y las lambdas asignadas a un único
nombre se miden aparte; el resto de lambdas suman a la función que las contiene. El código de
nivel de módulo y los cuerpos de clase no se miden.
"""

from __future__ import annotations

import ast
import os
import subprocess
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

EXCLUIDOS = frozenset({".venv", "__pycache__"})
RANGOS = (("A", 5), ("B", 10), ("C", 20), ("D", 30), ("E", 40))
# Fuente que no se puede analizar: sintaxis, bytes nulos o anidamiento que agota al parser.
INVALIDO = (SyntaxError, ValueError, RecursionError)


class ComplexityError(Exception):
    """Error de uso del análisis: ruta inexistente, referencia git inválida o falta de git."""


def rango(complejidad: int) -> str:
    """Rango como radon: A 1–5, B 6–10, C 11–20, D 21–30, E 31–40 y F 41 o más."""
    for letra, tope in RANGOS:
        if complejidad <= tope:
            return letra
    return "F"


@dataclass(frozen=True)
class Funcion:
    archivo: str
    linea: int
    nombre: str
    complejidad: int
    base: int | None = None
    nueva: bool = False

    @property
    def rango(self) -> str:
        return rango(self.complejidad)

    @property
    def delta(self) -> int | None:
        return None if self.base is None else self.complejidad - self.base

    @property
    def ubicacion(self) -> str:
        return f"{self.archivo}:{self.linea}"

    def to_dict(self) -> dict:
        return {
            "archivo": self.archivo,
            "linea": self.linea,
            "nombre": self.nombre,
            "complejidad": self.complejidad,
            "rango": self.rango,
            "base": self.base,
            "delta": self.delta,
            "nueva": self.nueva,
        }


# --- Cálculo -------------------------------------------------------------------------------


def _uno(_: ast.AST) -> int:
    return 1


PESOS: dict[type[ast.AST], Callable[[ast.AST], int]] = {
    ast.If: _uno,
    ast.For: _uno,
    ast.AsyncFor: _uno,
    ast.While: _uno,
    ast.ExceptHandler: _uno,
    ast.match_case: _uno,
    ast.IfExp: _uno,
    ast.comprehension: lambda nodo: 1 + len(nodo.ifs),
    ast.BoolOp: lambda nodo: len(nodo.values) - 1,
}


def _lambda_nombrada(nodo: ast.AST) -> tuple[str, ast.Lambda] | None:
    """`f = lambda …` (un único destino de tipo nombre): se mide aparte con ese nombre."""
    if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
        destino = nodo.targets[0]
    elif isinstance(nodo, ast.AnnAssign):
        destino = nodo.target
    else:
        return None
    if isinstance(destino, ast.Name) and isinstance(nodo.value, ast.Lambda):
        return destino.id, nodo.value
    return None


@dataclass
class _Ambito:
    nombre: str
    linea: int
    complejidad: int = 1


_Tarea = tuple[ast.AST, str, _Ambito | None]


def _separar(
    nodo: ast.AST, cuerpo: list[ast.AST], interior: tuple[str, _Ambito | None], exterior: _Tarea
) -> list[_Tarea]:
    """El cuerpo va al ámbito interior; decoradores, argumentos y bases, al que lo contiene."""
    ids = {id(hijo) for hijo in cuerpo}
    _, prefijo, actual = exterior
    return [
        (hijo, *interior) if id(hijo) in ids else (hijo, prefijo, actual)
        for hijo in ast.iter_child_nodes(nodo)
    ]


def _definir(
    nodo: ast.AST, nombre: str, cuerpo: list[ast.AST], tarea: _Tarea, ambitos: list[_Ambito]
) -> list[_Tarea]:
    ambito = _Ambito(tarea[1] + nombre, nodo.lineno)
    ambitos.append(ambito)
    return _separar(nodo, cuerpo, (f"{ambito.nombre}.", ambito), tarea)


def _paso(tarea: _Tarea, ambitos: list[_Ambito]) -> list[_Tarea]:
    """Procesa un nodo y devuelve sus hijos, cada uno con el ámbito al que suma."""
    nodo, prefijo, actual = tarea
    if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
        return _definir(nodo, nodo.name, nodo.body, tarea, ambitos)
    if isinstance(nodo, ast.ClassDef):
        return _separar(nodo, nodo.body, (f"{prefijo}{nodo.name}.", None), tarea)
    nombrada = _lambda_nombrada(nodo)
    if nombrada is not None:
        nombre, lam = nombrada
        resto = [(h, prefijo, actual) for h in ast.iter_child_nodes(nodo) if h is not lam]
        return resto + _definir(lam, nombre, [lam.body], tarea, ambitos)
    if actual is not None:
        peso = PESOS.get(type(nodo))
        actual.complejidad += peso(nodo) if peso else 0
    return [(hijo, prefijo, actual) for hijo in ast.iter_child_nodes(nodo)]


def medir(fuente: str | bytes, archivo: str = "") -> list[Funcion]:
    """Mide cada función de `fuente` en orden de aparición. Lanza SyntaxError si no es válida.

    El recorrido usa una pila explícita: un árbol muy profundo no agota la recursión.
    """
    ambitos: list[_Ambito] = []
    pila: list[_Tarea] = [(ast.parse(fuente), "", None)]
    while pila:
        pila += reversed(_paso(pila.pop(), ambitos))
    return [Funcion(archivo, a.linea, a.nombre, a.complejidad) for a in ambitos]


# --- Rutas y git ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True)
    except FileNotFoundError as exc:
        raise ComplexityError("git no está instalado") from exc


def _es_repo(root: Path) -> bool:
    proc = _git(root, "rev-parse", "--is-inside-work-tree")
    return proc.returncode == 0 and proc.stdout.strip() == b"true"


def _hay_git(root: Path) -> bool:
    try:
        return _es_repo(root)
    except ComplexityError:
        return False


def _lista_z(salida: bytes) -> list[str]:
    return [os.fsdecode(parte) for parte in salida.split(b"\0") if parte]


def _git_lista(root: Path, *args: str) -> list[str]:
    proc = _git(root, *args)
    if proc.returncode != 0:
        mensaje = proc.stderr.decode(errors="replace").strip()
        raise ComplexityError(f"git {' '.join(args)} falló: {mensaje}")
    return _lista_z(proc.stdout)


def _dir_excluido(nombre: str) -> bool:
    return nombre.startswith(".") or nombre in EXCLUIDOS


def _recorrer(directorio: Path) -> list[Path]:
    """`*.py` bajo `directorio`, sin entrar en directorios ocultos, `.venv` ni `__pycache__`."""
    encontrados = []
    for actual, dirs, archivos in os.walk(directorio):
        dirs[:] = sorted(d for d in dirs if not _dir_excluido(d))
        encontrados += [Path(actual) / a for a in sorted(archivos) if a.endswith(".py")]
    return encontrados


def _relativa(root: Path, ruta: Path) -> str:
    """Ruta relativa a la raíz; una ruta fuera del repositorio es un error de uso."""
    for candidata in (Path(os.path.abspath(ruta)), ruta.resolve()):
        if candidata.is_relative_to(root):
            return candidata.relative_to(root).as_posix()
    raise ComplexityError(f"la ruta está fuera del repositorio ({root}): {ruta}")


def _expandir(root: Path, rutas: Sequence[str]) -> list[str]:
    """Archivos de las rutas indicadas (relativas al directorio actual), relativos a la raíz."""
    archivos: list[str] = []
    for texto in rutas:
        ruta = Path(texto)
        if ruta.is_dir():
            archivos += [_relativa(root, p) for p in _recorrer(ruta)]
        elif ruta.is_file():
            archivos.append(_relativa(root, ruta))
        else:
            raise ComplexityError(f"no existe la ruta: {texto}")
    return archivos


def _por_defecto(root: Path) -> list[str]:
    if _hay_git(root):
        return _git_lista(root, "ls-files", "-z", "--", "*.py")
    return [_relativa(root, p) for p in _recorrer(root)]


def _verificar_ref(root: Path, ref: str) -> None:
    if not _es_repo(root):
        raise ComplexityError("--base requiere un repositorio git")
    proc = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if proc.returncode != 0:
        raise ComplexityError(f"referencia git inválida: {ref}")


def _en_dir_excluido(archivo: str) -> bool:
    return any(_dir_excluido(parte) for parte in Path(archivo).parts[:-1])


def _cambiados(root: Path, ref: str) -> dict[str, str]:
    """`*.py` cambiados frente a REF (ruta actual → ruta en REF), incluidos los no versionados.

    Los borrados se omiten; un renombrado conserva su ruta en REF para no perder la base. Los no
    versionados de directorios ocultos, `.venv` o `__pycache__` se ignoran, como en el recorrido.
    """
    campos = _git_lista(root, "diff", "--name-status", "-M", "--relative", "-z", ref, "--", "*.py")
    cambiados: dict[str, str] = {}
    i = 0
    while i < len(campos):
        estado = campos[i][:1]
        if estado in ("R", "C"):
            cambiados[campos[i + 2]] = campos[i + 1]
            i += 3
            continue
        if estado != "D":
            cambiados[campos[i + 1]] = campos[i + 1]
        i += 2
    otros = _git_lista(root, "ls-files", "--others", "--exclude-standard", "-z", "--", "*.py")
    cambiados.update((a, a) for a in otros if not _en_dir_excluido(a))
    return cambiados


def _dentro(archivo: str, filtros: Iterable[str]) -> bool:
    return any(f == "." or archivo == f or archivo.startswith(f"{f}/") for f in filtros)


def _base_de(root: Path, ref: str, archivo: str, ruta: str, avisos: list[str]) -> list[Funcion]:
    """Funciones de `ruta` en REF; vacío si no existía (todas las actuales serán nuevas)."""
    proc = _git(root, "show", f"{ref}:./{ruta}")
    if proc.returncode != 0:
        return []
    try:
        return medir(proc.stdout, ruta)
    except INVALIDO as exc:
        avisos.append(
            f"{archivo}: la versión de {ref} no es Python válido ({exc}); sus funciones aparecen "
            "como nuevas aunque puedan existir en la referencia"
        )
        return []


def _con_base(actuales: list[Funcion], base: list[Funcion]) -> list[Funcion]:
    """Empareja por nombre cualificado; si hay duplicados en el archivo, por orden."""
    pendientes: dict[str, list[int]] = defaultdict(list)
    for funcion in base:
        pendientes[funcion.nombre].append(funcion.complejidad)
    emparejadas = []
    for funcion in actuales:
        cola = pendientes[funcion.nombre]
        valor = cola.pop(0) if cola else None
        emparejadas.append(replace(funcion, base=valor, nueva=valor is None))
    return emparejadas


# --- Informe -------------------------------------------------------------------------------


@dataclass
class Informe:
    funciones: list[Funcion]
    avisos: list[str]
    umbral: int | None = None
    ref: str | None = None

    def en_alcance_del_umbral(self, funcion: Funcion) -> bool:
        if self.ref is None:
            return True
        return funcion.nueva or (funcion.delta or 0) > 0

    @property
    def superan(self) -> list[Funcion]:
        if self.umbral is None:
            return []
        return [
            f
            for f in self.funciones
            if f.complejidad > self.umbral and self.en_alcance_del_umbral(f)
        ]

    @property
    def resumen(self) -> dict:
        valores = [f.complejidad for f in self.funciones]
        media = round(sum(valores) / len(valores), 1) if valores else 0.0
        return {"funciones": len(valores), "media": media, "maximo": max(valores, default=0)}

    def to_dict(self) -> dict:
        return {
            "funciones": [f.to_dict() for f in self.funciones],
            "resumen": self.resumen,
            "avisos": list(self.avisos),
            "umbral": self.umbral,
            "superan": [f.to_dict() for f in self.superan],
        }


def _medir_archivo(root: Path, archivo: str, avisos: list[str]) -> list[Funcion] | None:
    try:
        return medir((root / archivo).read_bytes(), archivo)
    except INVALIDO as exc:
        avisos.append(f"{archivo}: no es Python válido ({exc}); se omite")
    except OSError as exc:
        avisos.append(f"{archivo}: no se puede leer ({exc.strerror}); se omite")
    return None


def _expandir_filtros(root: Path, rutas: Sequence[str]) -> list[str]:
    for texto in rutas:
        if not Path(texto).exists():
            raise ComplexityError(f"no existe la ruta: {texto}")
    return [_relativa(root, Path(texto)) for texto in rutas]


def _archivos(root: Path, rutas: Sequence[str], base: str | None) -> dict[str, str | None]:
    """Archivos del alcance → su ruta en REF (None sin `--base`)."""
    if base is None:
        return dict.fromkeys(_expandir(root, rutas) if rutas else _por_defecto(root))
    _verificar_ref(root, base)
    archivos = _cambiados(root, base)
    if rutas:
        filtros = _expandir_filtros(root, rutas)
        archivos = {a: b for a, b in archivos.items() if _dentro(a, filtros)}
    return archivos


def analizar(
    root: Path,
    rutas: Sequence[str] = (),
    *,
    base: str | None = None,
    umbral: int | None = None,
) -> Informe:
    """Mide las funciones del alcance y, con `base`, su complejidad en esa referencia."""
    root = root.resolve()
    avisos: list[str] = []
    funciones: list[Funcion] = []
    for archivo, ruta_base in _archivos(root, rutas, base).items():
        if not (root / archivo).is_file():
            continue  # borrado en el árbol de trabajo
        actuales = _medir_archivo(root, archivo, avisos)
        if actuales is None:
            continue
        if base is not None and ruta_base is not None:
            anteriores = _base_de(root, base, archivo, ruta_base, avisos)
            actuales = _con_base(actuales, anteriores)
        funciones += actuales
    funciones.sort(key=lambda f: (-f.complejidad, f.archivo, f.linea))
    return Informe(funciones, avisos, umbral, base)


# --- Salida de texto -----------------------------------------------------------------------


def _sufijo(funcion: Funcion, con_base: bool) -> str:
    if not con_base:
        return ""
    if funcion.nueva:
        return "  (nueva)"
    return f"  (base {funcion.base}, {funcion.delta:+d})"


def _linea(funcion: Funcion, ancho: int, con_base: bool) -> str:
    texto = f"{funcion.rango} {funcion.complejidad:>3}  {funcion.ubicacion:<{ancho}}  "
    return (texto + funcion.nombre + _sufijo(funcion, con_base)).rstrip()


def _umbral(informe: Informe) -> list[str]:
    if informe.umbral is None:
        return []
    superan = informe.superan
    if not superan:
        return [f"Umbral {informe.umbral}: ninguna función lo supera."]
    lineas = [f"Superan el umbral {informe.umbral}: {len(superan)} función(es)"]
    lineas += [f"  - {f.ubicacion}  {f.nombre}  ({f.complejidad})" for f in superan]
    return lineas


def render(informe: Informe) -> str:
    """Tabla por complejidad descendente, resumen y, con umbral, las funciones que lo superan."""
    con_base = informe.ref is not None
    ancho = max((len(f.ubicacion) for f in informe.funciones), default=0)
    lineas = [_linea(f, ancho, con_base) for f in informe.funciones]
    if not lineas:
        lineas.append("Sin funciones que analizar.")
    resumen = informe.resumen
    lineas.append("")
    lineas.append(
        f"Resumen: {resumen['funciones']} función(es) · media {resumen['media']:.1f} · "
        f"máximo {resumen['maximo']}"
    )
    lineas += _umbral(informe)
    return "\n".join(lineas)
