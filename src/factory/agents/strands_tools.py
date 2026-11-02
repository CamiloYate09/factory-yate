"""Herramientas confinadas del backend Strands (diseño D2, D3, D5 y D6).

Las herramientas integradas de `strands-harness` actúan sobre todo el host y su shell no tiene
restricciones; por eso el backend usa estas seis funciones propias. Son Python puro, sin
dependencia de `strands`: el runner las envuelve con `@strands.tool` al crear el agente.

- `PathPolicy`: lectura y escritura dentro de `cwd`; solo lectura en `add_dirs`; rutas
  resueltas con `realpath` (enlaces simbólicos y `..`) y reglas `Read/Edit/Write(...)` denegadas.
- `ShellPolicy`: solo prefijos `Bash(<p>:*)` permitidos, sin metacaracteres, con `shell=False`.
- `plan_tools`: traduce las listas de herramientas de Claude Code con fallo cerrado.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from factory.util import command_env

READ_LIMIT = 2000
LINE_MAX_CHARS = 2000
GLOB_LIMIT = 500
GREP_LIMIT = 200
GREP_FILE_MAX_BYTES = 2_000_000
SHELL_OUTPUT_MAX_CHARS = 30_000
SHELL_TIMEOUT_S = 600
SKIP_DIRS = {".git"}
SHELL_POLL_S = 0.2
SHELL_KILL_WAIT_S = 2.0
SEARCH_TIMEOUT_S = 30

# `re` no suelta el GIL: un patrón costoso del modelo dentro del proceso congelaría el tiempo límite
# y Ctrl-C. Por eso `grep` y `glob` lo evalúan en este proceso hijo, que se puede matar.
SEARCH_WORKER = r"""
import json, os, re, sys

job = json.load(sys.stdin)
keep = re.compile(job["keep"], job["keep_flags"]) if job["keep"] else None
pattern = re.compile(job["pattern"], job["flags"]) if job["pattern"] else None
lines = []
for shown, real, label in job["files"]:
    if keep and not keep.match(shown):
        continue
    if pattern is None:
        lines.append(label)
        continue
    if os.path.getsize(real) > job["max_bytes"]:
        continue
    try:
        with open(real, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if pattern.search(line):
                    text = line.rstrip("\n")[: job["max_chars"]]
                    lines.append(f"{label}:{number}:{text}")
    except (UnicodeDecodeError, OSError):
        continue
    if len(lines) > job["limit"]:
        break
json.dump(lines, sys.stdout)
"""
# Credenciales que Strands necesita en el entorno del proceso y que los comandos del agente no.
CREDENTIAL_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
CREDENTIAL_ENV_PREFIXES = ("AWS_",)

# Metacaracteres que permitirían encadenar, redirigir o sustituir comandos (D5).
SHELL_FORBIDDEN = (";", "&", "|", "<", ">", "`", "$", "\n", "\r")

RULE_RE = re.compile(r"^(?P<name>[A-Za-z][\w-]*)(?:\((?P<arg>.*)\))?$", re.DOTALL)
FILE_TOOLS = {"Read": "read", "Glob": "glob", "Grep": "grep", "Edit": "edit", "Write": "write"}
EDIT_ALIASES = {"MultiEdit": "edit"}
WRITE_RULES = ("Edit", "Write", "MultiEdit")
TOOL_ORDER = ("read", "glob", "grep", "edit", "write", "shell")


class ToolError(Exception):
    """Error devuelto al agente como resultado de la herramienta; nunca detiene el runner."""


class UntranslatableTools(ValueError):
    """Herramientas permitidas sin equivalente confinado: la invocación no se hace (D6)."""

    def __init__(self, names: list[str]):
        self.names = names
        super().__init__(
            "herramientas sin traducción al backend strands: "
            + ", ".join(names)
            + '. Quítalas de allowed_tools del rol o usa backend = "claude-code".'
        )


def parse_rule(rule: str) -> tuple[str, str | None]:
    match = RULE_RE.match(rule.strip())
    if not match:
        return rule.strip(), None
    return match.group("name"), match.group("arg")


# --------------------------------------------------------------------------- rutas


def _glob_regex(pattern: str, ignore_case: bool = False) -> re.Pattern[str]:
    """Glob de rutas absolutas: `**` cruza directorios, `*` y `?` no."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("(?:/.*)?")
            i += 3
        elif pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z", re.IGNORECASE if ignore_case else 0)


def _realpath_prefix(pattern: str) -> str:
    """Resuelve la parte literal del patrón, para comparar con rutas pasadas por `realpath`."""
    parts = pattern.split("/")
    literal = []
    for part in parts:
        if any(ch in part for ch in "*?["):
            break
        literal.append(part)
    rest = parts[len(literal) :]
    base = os.path.realpath("/".join(literal) or "/")
    return "/".join([base.rstrip("/"), *rest]) if rest else base


def _rule_pattern(arg: str, cwd: str) -> re.Pattern[str]:
    """Ruta de una regla de Claude Code: `//abs`, `~/home`, `/relativa` o `relativa` a `cwd`."""
    if arg.startswith("//"):
        absolute = "/" + arg.lstrip("/")
    elif arg.startswith("~/"):
        absolute = os.path.expanduser(arg)
    else:
        absolute = os.path.join(cwd, arg.lstrip("/"))
    # Sin distinguir mayúsculas: en APFS o NTFS `FEATURE_LIST.json` abre `feature_list.json`,
    # y denegar de más es el lado seguro.
    return _glob_regex(_realpath_prefix(os.path.normpath(absolute)), ignore_case=True)


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _inside_any_case(path: str, root: str) -> bool:
    """Para denegaciones: un cambio de mayúsculas no saca la ruta de la raíz protegida."""
    return _inside(path.casefold(), root.casefold())


@dataclass
class PathPolicy:
    cwd: Path
    read_only: list[Path] = field(default_factory=list)
    denied_read: list[str] = field(default_factory=list)
    denied_write: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._cwd = os.path.realpath(self.cwd)
        self._ro = [os.path.realpath(p) for p in self.read_only]
        self._deny_read = [_rule_pattern(rule, self._cwd) for rule in self.denied_read]
        self._deny_write = [_rule_pattern(rule, self._cwd) for rule in self.denied_write]

    def resolve(self, path: str | os.PathLike[str]) -> str:
        raw = os.path.expanduser(os.fspath(path))
        joined = raw if os.path.isabs(raw) else os.path.join(self._cwd, raw)
        return os.path.realpath(joined)

    def display(self, real: str) -> str:
        return os.path.relpath(real, self._cwd) if _inside(real, self._cwd) else real

    def can_read(self, real: str) -> bool:
        inside = _inside(real, self._cwd) or any(_inside(real, ro) for ro in self._ro)
        return inside and not any(p.match(real) for p in self._deny_read)

    def check_read(self, path: str | os.PathLike[str]) -> str:
        real = self.resolve(path)
        if not self.can_read(real):
            raise ToolError(f"lectura denegada: {path} está fuera de las rutas permitidas")
        return real

    def check_write(self, path: str | os.PathLike[str]) -> str:
        real = self.resolve(path)
        if not _inside(real, self._cwd) or any(_inside_any_case(real, ro) for ro in self._ro):
            raise ToolError(f"escritura denegada: {path} está fuera del directorio de trabajo")
        relative = os.path.relpath(real, self._cwd)
        if any(part.casefold() == ".git" for part in relative.split(os.sep)):
            # En un worktree `.git` apunta al repo principal: reescribirlo desviaría el git del
            # motor, y en un repo normal daría acceso a hooks y config.
            raise ToolError(f"escritura denegada: {path} es metadato de git")
        if any(p.match(real) for p in self._deny_write):
            raise ToolError(f"escritura denegada: {path} está protegido para este rol")
        return real


# --------------------------------------------------------------------------- shell


def _shell_rule(arg: str) -> tuple[tuple[str, ...], bool]:
    """`git diff:*` → prefijo (`git`, `diff`); `git status` → comando exacto.

    Una regla que `shlex` no puede interpretar (comillas sin cerrar) da tokens vacíos, que
    `plan_tools` trata como intraducible.
    """
    prefix = arg.endswith(":*")
    try:
        tokens = tuple(shlex.split(arg[:-2] if prefix else arg))
    except ValueError:
        tokens = ()
    return tokens, prefix


@dataclass
class ShellPolicy:
    cwd: Path
    allowed: list[tuple[tuple[str, ...], bool]]
    denied: list[tuple[tuple[str, ...], bool]] = field(default_factory=list)
    timeout_s: float = SHELL_TIMEOUT_S
    # El runner la activa al agotar el tiempo de la invocación: mata el comando en curso.
    cancel: threading.Event | None = None

    @staticmethod
    def _matches(argv: list[str], rule: tuple[tuple[str, ...], bool]) -> bool:
        tokens, prefix = rule
        if not tokens:
            return False
        return tuple(argv[: len(tokens)]) == tokens and (prefix or len(argv) == len(tokens))

    def check(self, command: str) -> list[str]:
        if any(ch in command for ch in SHELL_FORBIDDEN):
            raise ToolError(
                "comando rechazado: no se admiten encadenamientos, redirecciones ni sustituciones "
                "(; & | < > ` $ ni saltos de línea); ejecuta un solo comando"
            )
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise ToolError(f"comando rechazado: no se puede interpretar ({exc})") from exc
        if not argv:
            raise ToolError("comando rechazado: está vacío")
        if any(self._matches(argv, rule) for rule in self.denied):
            raise ToolError(f"comando rechazado: '{command}' está denegado para este rol")
        if not any(self._matches(argv, rule) for rule in self.allowed):
            permitidos = ", ".join(
                " ".join(tokens) + (" …" if prefix else "") for tokens, prefix in self.allowed
            )
            raise ToolError(f"comando rechazado: solo se permiten: {permitidos}")
        return argv

    def run(self, command: str) -> str:
        argv = self.check(command)
        if self.cancel is not None and self.cancel.is_set():
            raise ToolError("invocación cancelada")
        env = command_env(self.cwd)
        for key in list(env):
            if key in CREDENTIAL_ENV or key.startswith(CREDENTIAL_ENV_PREFIXES):
                del env[key]
        try:
            proc = _spawn(argv, self.cwd, env)
        except FileNotFoundError as exc:
            raise ToolError(f"no se encontró el ejecutable '{argv[0]}'") from exc
        try:
            stdout, stderr = _wait_killable(proc, self.cancel, self.timeout_s)
        except _Stopped as exc:
            raise ToolError(f"{exc}: se detuvo '{command}'") from None
        output = f"código de salida: {proc.returncode}\n{stdout}"
        if stderr:
            output += f"\n[stderr]\n{stderr}"
        return _clip(output, SHELL_OUTPUT_MAX_CHARS)


class _Stopped(Exception):
    """El proceso hijo se mató por cancelación o por tiempo agotado."""


def _spawn(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # su propio grupo: se mata con todos sus hijos
    )


def _wait_killable(
    proc: subprocess.Popen,
    cancel: threading.Event | None,
    timeout_s: float,
    stdin: str | None = None,
) -> tuple[str, str]:
    """Salida del hijo; lo mata con todo su grupo si se activa `cancel` o vence el tiempo."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return proc.communicate(input=stdin, timeout=SHELL_POLL_S)
        except subprocess.TimeoutExpired:
            stdin = None  # `communicate` no admite repetir la entrada: ya se está enviando
            cancelled = cancel is not None and cancel.is_set()
            if cancelled or time.monotonic() >= deadline:
                _kill_group(proc)
                try:
                    proc.communicate(timeout=SHELL_KILL_WAIT_S)
                except subprocess.TimeoutExpired:
                    pass  # un descendiente con otra sesión conserva los pipes: no lo esperamos
                raise _Stopped("invocación cancelada" if cancelled else "tiempo agotado") from None


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[… recortado: {len(text) - limit} caracteres más]"


# --------------------------------------------------------------------------- herramientas


@dataclass
class Toolset:
    """Las herramientas disponibles para una invocación y sus políticas."""

    names: list[str]
    paths: PathPolicy
    shell_policy: ShellPolicy | None = None
    cancel: threading.Event | None = None
    search_timeout_s: float = SEARCH_TIMEOUT_S

    def functions(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.names}

    def _walk(self, base: str):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                real = os.path.realpath(os.path.join(dirpath, name))
                if self.paths.can_read(real) and os.path.isfile(real):
                    yield os.path.join(dirpath, name), real

    def _search(
        self,
        files: list[tuple[str, str, str]],
        keep: re.Pattern[str] | None,
        pattern: re.Pattern[str] | None = None,
    ) -> list[str]:
        """Evalúa los patrones del modelo en el proceso hijo (ver `SEARCH_WORKER`)."""
        job = {
            "files": files,
            "keep": keep.pattern if keep else None,
            "keep_flags": keep.flags if keep else 0,
            "pattern": pattern.pattern if pattern else None,
            "flags": pattern.flags if pattern else 0,
            "limit": GREP_LIMIT,
            "max_bytes": GREP_FILE_MAX_BYTES,
            "max_chars": LINE_MAX_CHARS,
        }
        proc = _spawn([sys.executable, "-I", "-S", "-c", SEARCH_WORKER], self.paths.cwd, {})
        try:
            stdout, stderr = _wait_killable(
                proc, self.cancel, self.search_timeout_s, json.dumps(job)
            )
        except _Stopped as exc:
            raise ToolError(
                f"{exc}: la búsqueda es demasiado costosa; simplifica el patrón"
            ) from None
        if proc.returncode != 0:
            raise ToolError(f"la búsqueda falló: {stderr.strip()[-300:]}")
        return json.loads(stdout)

    def read(self, path: str, offset: int = 1, limit: int = READ_LIMIT) -> str:
        """Lee un archivo de texto y devuelve sus líneas numeradas.

        Args:
            path: Ruta del archivo, relativa al directorio de trabajo o absoluta.
            offset: Primera línea (desde 1).
            limit: Número máximo de líneas.
        """
        real = self.paths.check_read(path)
        if not os.path.isfile(real):
            raise ToolError(f"no existe el archivo {path}")
        try:
            with open(real, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except UnicodeDecodeError as exc:
            raise ToolError(f"{path} no es un archivo de texto UTF-8") from exc
        start = max(offset, 1)
        chunk = lines[start - 1 : start - 1 + max(limit, 1)]
        numbered = [f"{start + i:>6}\t{line[:LINE_MAX_CHARS]}" for i, line in enumerate(chunk)]
        if not numbered:
            return f"({path}: sin líneas desde la {start}; el archivo tiene {len(lines)})"
        return "\n".join(numbered)

    def glob(self, pattern: str, path: str = ".") -> str:
        """Lista los archivos que coinciden con un patrón glob (`**` cruza directorios).

        Args:
            pattern: Patrón relativo a `path`, por ejemplo `src/**/*.py`.
            path: Directorio base; por defecto, el directorio de trabajo.
        """
        base = self.paths.check_read(path)
        regex = _glob_regex(os.path.join(base, pattern))
        files = [(shown, real, self.paths.display(real)) for shown, real in self._walk(base)]
        found = self._search(files, regex)
        lines = found[:GLOB_LIMIT]
        if len(found) > GLOB_LIMIT:
            lines.append(f"[… {len(found) - GLOB_LIMIT} archivos más]")
        return "\n".join(lines) or "(sin coincidencias)"

    def grep(
        self, pattern: str, path: str = ".", glob: str | None = None, ignore_case: bool = False
    ) -> str:
        """Busca una expresión regular en los archivos y devuelve `ruta:línea:texto`.

        Args:
            pattern: Expresión regular de Python.
            path: Archivo o directorio donde buscar; por defecto, el directorio de trabajo.
            glob: Filtro opcional de archivos, por ejemplo `**/*.py`.
            ignore_case: Ignorar mayúsculas y minúsculas.
        """
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            raise ToolError(f"expresión regular inválida: {exc}") from exc
        base = self.paths.check_read(path)
        walked = [(base, base)] if os.path.isfile(base) else list(self._walk(base))
        files = [(shown, real, self.paths.display(real)) for shown, real in walked]
        keep = _glob_regex(os.path.join(base, glob)) if glob else None
        matches = self._search(files, keep, regex)
        if len(matches) > GREP_LIMIT:
            return "\n".join(matches[:GREP_LIMIT]) + "\n[… más coincidencias; acota la búsqueda]"
        return "\n".join(matches) or "(sin coincidencias)"

    def edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """Sustituye un texto exacto en un archivo existente.

        Args:
            path: Ruta del archivo.
            old_string: Texto exacto a sustituir; debe ser único salvo con `replace_all`.
            new_string: Texto nuevo.
            replace_all: Sustituir todas las apariciones.
        """
        real = self.paths.check_write(path)
        if not os.path.isfile(real):
            raise ToolError(f"no existe el archivo {path}; usa write para crearlo")
        with open(real, encoding="utf-8") as handle:
            content = handle.read()
        count = content.count(old_string) if old_string else 0
        if count == 0:
            raise ToolError(f"old_string no aparece en {path}")
        if count > 1 and not replace_all:
            raise ToolError(
                f"old_string aparece {count} veces en {path}; amplíalo o usa replace_all"
            )
        updated = content.replace(old_string, new_string, -1 if replace_all else 1)
        with open(real, "w", encoding="utf-8") as handle:
            handle.write(updated)
        return f"{self.paths.display(real)}: {count if replace_all else 1} sustitución(es)"

    def write(self, path: str, content: str) -> str:
        """Crea o sobrescribe un archivo con el contenido dado.

        Args:
            path: Ruta del archivo; los directorios intermedios se crean.
            content: Contenido completo del archivo.
        """
        real = self.paths.check_write(path)
        parent = os.path.dirname(real)
        os.makedirs(parent, exist_ok=True)
        if os.path.realpath(parent) != parent:  # un directorio intermedio era un enlace
            raise ToolError(f"escritura denegada: {path} sale del directorio de trabajo")
        with open(real, "w", encoding="utf-8") as handle:
            handle.write(content)
        return f"{self.paths.display(real)}: {len(content)} caracteres escritos"

    def shell(self, command: str) -> str:
        """Ejecuta un único comando permitido en el directorio de trabajo, sin shell.

        Args:
            command: El comando, por ejemplo `git diff --stat`.
        """
        assert self.shell_policy is not None
        return self.shell_policy.run(command)


def plan_tools(
    allowed: list[str],
    denied: list[str],
    cwd: Path,
    add_dirs: list[Path] | None = None,
    shell_timeout_s: float = SHELL_TIMEOUT_S,
    cancel: threading.Event | None = None,
) -> Toolset:
    """Traduce las reglas de un rol a un `Toolset`; lanza `UntranslatableTools` (D6)."""
    enabled: set[str] = set()
    untranslatable: list[str] = []
    shell_allowed: list[tuple[tuple[str, ...], bool]] = []
    for rule in allowed:
        name, arg = parse_rule(rule)
        tool = FILE_TOOLS.get(name) or EDIT_ALIASES.get(name)
        if tool and arg is None:
            enabled.add(tool)
        elif name == "Bash" and arg and _shell_rule(arg)[0]:
            shell_allowed.append(_shell_rule(arg))
        else:
            untranslatable.append(rule)  # `Bash` a secas sería un shell sin restricciones
    if untranslatable:
        raise UntranslatableTools(untranslatable)

    shell_denied: list[tuple[tuple[str, ...], bool]] = []
    denied_read: list[str] = []
    denied_write: list[str] = []
    for rule in denied:
        name, arg = parse_rule(rule)
        if arg is None:
            enabled.discard(FILE_TOOLS.get(name) or EDIT_ALIASES.get(name) or "")
            if name == "Bash":
                shell_allowed = []
        elif name == "Bash":
            rule_tokens = _shell_rule(arg)
            if not rule_tokens[0]:  # una denegación ilegible no se ignora: fallo cerrado
                raise UntranslatableTools([rule])
            shell_denied.append(rule_tokens)
        elif name == "Read":
            denied_read.append(arg)
        elif name in WRITE_RULES:
            denied_write.append(arg)
        # El resto de reglas denegadas se refieren a herramientas que este backend no ofrece.

    paths = PathPolicy(cwd, list(add_dirs or []), denied_read, denied_write)
    shell = None
    if shell_allowed:
        enabled.add("shell")
        shell = ShellPolicy(cwd, shell_allowed, shell_denied, shell_timeout_s, cancel)
    return Toolset([t for t in TOOL_ORDER if t in enabled], paths, shell, cancel)
