"""Mapa de la biblioteca (spec library-map): metadatos versionables, nunca texto de los libros.

Cada línea del mapa se CONSTRUYE desde una lista blanca de campos; jamás se copia una línea
del catálogo para borrarle claves. Así un campo nuevo del vault (por ejemplo, un resumen) no
puede colarse en git. `doctor` vuelve a validar el mapa con las mismas listas.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from factory.brain import BrainError
from factory.util import atomic_write_text

NOTE_FIELDS = (
    "path",
    "book_id",
    "type",
    "title",
    "chapter",
    "chapter_title",
    "section_path",
    "pages",
    "tokens",
    "keywords",
)
BOOK_FIELDS = (  # sin `subtitle`: en el vault real a veces trae texto de una página del libro
    "slug",
    "title",
    "authors",
    "domains",
    "pages",
    "chapters",
    "notes",
    "words",
    "tokens",
)
MAP_FILES = ("_catalog.jsonl", "_books.json", "_map.json", "llms.txt", "AGENTS.md", ".gitignore")
MAX_HEADING_WORDS = 20  # el encabezado real más largo del vault tiene 17
MAX_KEYWORDS = 12
MAX_AUTHORS = 25
# Formatos estrictos: ningún campo salvo los encabezados puede contener una frase.
SLUG_RE = re.compile(r"[\w.+#/-]{1,60}")  # keywords reales: 89.425, todas con esta forma
ID_RE = re.compile(r"[\w.-]{1,80}")
CHAPTER_RE = re.compile(r"[\w.-]{1,12}")
TYPE_RE = re.compile(r"[a-z_-]{1,20}")
PATH_RE = re.compile(r"[\w./-]{1,300}\.md")
AUTHOR_RE = re.compile(r"[^\n]{1,80}")
# Un .gitignore propio: git solo ve los archivos del mapa (nunca .DS_Store ni .obsidian/).
GITIGNORE = "*\n" + "".join(f"!{name}\n" for name in MAP_FILES)

AGENTS_GUIDE = """# Mapa de la biblioteca

Índice de la biblioteca técnica del cerebro principal: qué libros, capítulos y secciones hay y
en qué páginas está cada tema. **No contiene texto de los libros**: los libros no se versionan.
Lo genera `factory brain import`; no lo edites a mano (`factory doctor` lo valida).

## Estructura

```
_catalog.jsonl  <- 1 línea JSON por nota: path, book_id, type, title, chapter, chapter_title,
                   section_path, pages, tokens, keywords
_books.json     <- libros: slug, title, authors, domains, pages, chapters, notes, words,
                   tokens
_map.json       <- huella del catálogo de origen y recuentos
llms.txt        <- índice compacto por dominio
```

## Cómo usarlo

1. `factory brain search "<consulta en inglés>"` o `grep -i "<término>" _catalog.jsonl`.
2. Cada resultado da la cita (*Libro* · cap. N · pp. A–B) para consultar tu ejemplar.
3. El texto completo solo está en el equipo que tenga su copia importada
   (`factory brain import <vault>`), en `brain-principal/<path>`.
"""


@dataclass
class MapResult:
    path: str
    notes: int
    books: int
    changed: list[str] = field(default_factory=list)
    dropped: int = 0  # notas del catálogo descartadas por una ruta fuera de formato


def _heading(value) -> str | None:
    if value is None:
        return None
    words = " ".join(str(value).split()).split(" ")
    return " ".join(words[:MAX_HEADING_WORDS])


def _int(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _match(pattern: re.Pattern, value) -> str | None:
    """El valor como texto si cumple el formato estricto; si no, se descarta."""
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value)
    return text if pattern.fullmatch(text) else None


def _list(value) -> list:
    return value if isinstance(value, list) else []  # nunca se recorre una cadena


def map_note(raw: dict) -> dict | None:
    """Línea del mapa construida campo a campo desde la lista blanca (None si la ruta no vale)."""
    path = _match(PATH_RE, raw.get("path"))
    if path is None:
        return None
    keywords = [k for k in (_match(SLUG_RE, x) for x in _list(raw.get("keywords"))) if k]
    pages = [p for p in (_int(x) for x in _list(raw.get("pages"))) if p is not None]
    return {
        "path": path,
        "book_id": _match(ID_RE, raw.get("book_id")) or "",
        "type": _match(TYPE_RE, raw.get("type")) or "",
        "title": _heading(raw.get("title")) or path,
        "chapter": _match(CHAPTER_RE, raw.get("chapter")),
        "chapter_title": _heading(raw.get("chapter_title")),
        "section_path": [h for h in (_heading(x) for x in _list(raw.get("section_path"))) if h],
        "pages": pages[:2],
        "tokens": _int(raw.get("tokens")) or 0,
        "keywords": list(dict.fromkeys(keywords))[:MAX_KEYWORDS],
    }


def map_book(raw: dict) -> dict:
    authors = [a for a in (_match(AUTHOR_RE, _heading(x)) for x in _list(raw.get("authors"))) if a]
    domains = [d for d in (_match(ID_RE, x) for x in _list(raw.get("domains"))) if d]
    return {
        "slug": _match(ID_RE, raw.get("slug")) or "",
        "title": _heading(raw.get("title")) or "",
        "authors": list(dict.fromkeys(authors))[:MAX_AUTHORS],
        "domains": list(dict.fromkeys(domains)),
        "pages": _int(raw.get("pages")),
        "chapters": _int(raw.get("chapters")),
        "notes": _int(raw.get("notes")),
        "words": _int(raw.get("words")),
        "tokens": _int(raw.get("tokens")),
    }


def _llms(books: list[dict]) -> str:
    lines = [
        "# Mapa de la biblioteca",
        "",
        "> Índice sin texto de los libros. Lee AGENTS.md; usa _catalog.jsonl para localizar "
        "notas y citarlas.",
        "",
    ]
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for book in books:
        by_domain[(book["domains"] or ["otros"])[0]].append(book)
    for domain in sorted(by_domain):
        lines += [f"## {domain}", ""]
        for book in sorted(by_domain[domain], key=lambda b: b["title"].lower()):
            authors = ", ".join(book["authors"]) or "—"
            lines.append(
                f"- {book['title']} — {authors}: {book['chapters'] or '?'} capítulos, "
                f"{book['notes'] or '?'} notas, ~{book['tokens'] or 0:,} tokens"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


SHA_RE = re.compile(r"[0-9a-f]{64}")


def _catalog_text(entries: list[dict]) -> str:
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)


def _books_text(books: list[dict]) -> str:
    return json.dumps(books, ensure_ascii=False, indent=2) + "\n"


def _meta_text(sha: str, notes: int, books: int) -> str:
    meta = {
        "source_catalog_sha256": sha,
        "notes": notes,
        "books": books,
        "note_fields": list(NOTE_FIELDS),
        "book_fields": list(BOOK_FIELDS),
    }
    return json.dumps(meta, ensure_ascii=False, indent=2) + "\n"


def render_map(principal: Path) -> dict[str, str]:
    """Contenido de cada archivo del mapa (determinista: mismo vault → mismos bytes)."""
    catalog = principal / "_catalog.jsonl"
    if not catalog.is_file():
        raise BrainError(f"No hay catálogo en {principal}: importa primero el cerebro principal.")
    raw_catalog = catalog.read_bytes()
    notes = [json.loads(line) for line in raw_catalog.decode("utf-8").splitlines() if line.strip()]
    mapped = (map_note(n) for n in notes if isinstance(n, dict))
    entries = sorted((n for n in mapped if n), key=lambda n: n["path"])
    books_file = principal / "_books.json"
    raw_books = json.loads(books_file.read_text(encoding="utf-8")) if books_file.is_file() else []
    if isinstance(raw_books, dict):  # formato antiguo: {slug: {...}}
        raw_books = [{"slug": k, **v} for k, v in raw_books.items() if isinstance(v, dict)]
    books = sorted((map_book(b) for b in raw_books if isinstance(b, dict)), key=lambda b: b["slug"])
    sha = hashlib.sha256(raw_catalog).hexdigest()
    return {
        "_catalog.jsonl": _catalog_text(entries),
        "_books.json": _books_text(books),
        "_map.json": _meta_text(sha, len(entries), len(books)),
        "llms.txt": _llms(books),
        "AGENTS.md": AGENTS_GUIDE,
        ".gitignore": GITIGNORE,
    }


def build_map(principal: Path, map_dir: Path) -> MapResult:
    """Regenera el mapa; solo reescribe los archivos cuyo contenido cambió."""
    files = render_map(principal)
    map_dir.mkdir(parents=True, exist_ok=True)
    changed = []
    for name, text in files.items():
        target = map_dir / name
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            atomic_write_text(target, text)
            changed.append(name)
    meta = json.loads(files["_map.json"])
    raw = (principal / "_catalog.jsonl").read_text(encoding="utf-8")
    dropped = sum(1 for line in raw.splitlines() if line.strip()) - meta["notes"]
    return MapResult(str(map_dir), meta["notes"], meta["books"], changed, dropped)


def _candidates(map_dir: Path) -> list[str]:
    """Archivos del mapa que acabarían en git (o, fuera de un repo, los no ocultos)."""
    probe = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "."],
        cwd=map_dir,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return sorted(line for line in probe.stdout.splitlines() if line)
    return sorted(
        p.relative_to(map_dir).as_posix()
        for p in map_dir.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(map_dir).parts)
    )


def problems(map_dir: Path) -> list[str]:
    """Infracciones del mapa (para `doctor`). Vacío si el mapa es válido o no existe.

    Se compara el TEXTO de cada archivo con su forma canónica, no el JSON ya interpretado:
    así no cabe un párrafo en una clave repetida (JSON se queda con el último valor), en un
    valor de `_map.json` ni en una guía editada. Cada línea y cada libro deben ser idénticos
    a lo que produciría la generación, con sus formatos estrictos.
    """
    if not map_dir.is_dir():
        return []
    unreadable = []
    for name in MAP_FILES:
        try:
            if (map_dir / name).is_file():
                (map_dir / name).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            unreadable.append(f"{name}: no es UTF-8 válido")
    if unreadable:
        return unreadable
    found = [
        f"{relative}: archivo no permitido en el mapa (bórralo)"
        for relative in _candidates(map_dir)
        if relative not in MAP_FILES
    ]
    found += [f"{name}: falta en el mapa" for name in MAP_FILES if not (map_dir / name).is_file()]
    notes = 0
    catalog = map_dir / "_catalog.jsonl"
    if catalog.is_file():
        for number, line in enumerate(catalog.read_text(encoding="utf-8").split("\n"), 1):
            if not line:
                continue
            notes += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                found.append(f"_catalog.jsonl línea {number}: JSON inválido")
                continue
            if not isinstance(entry, dict):
                found.append(f"_catalog.jsonl línea {number}: no es un objeto")
                continue
            extra = sorted(set(entry) - set(NOTE_FIELDS))
            rebuilt = map_note(entry)
            if extra:
                found.append(f"_catalog.jsonl línea {number}: campo no permitido {extra}")
            elif rebuilt != entry:
                fields = sorted(k for k in NOTE_FIELDS if (rebuilt or {}).get(k) != entry.get(k))
                found.append(f"_catalog.jsonl línea {number}: valor fuera de formato en {fields}")
            elif line != json.dumps(rebuilt, ensure_ascii=False):
                found.append(
                    f"_catalog.jsonl línea {number}: texto distinto del que genera factory "
                    "(¿clave repetida o formato manual?)"
                )
    books: list | None = None
    books_file = map_dir / "_books.json"
    if books_file.is_file():
        text = books_file.read_text(encoding="utf-8")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
            found.append("_books.json: JSON inválido")
        if parsed is not None and not (
            isinstance(parsed, list) and all(isinstance(b, dict) for b in parsed)
        ):
            found.append("_books.json: debe ser una lista de libros")
        elif parsed is not None:
            for index, book in enumerate(parsed, 1):
                extra = sorted(set(book) - set(BOOK_FIELDS))
                if extra:
                    found.append(f"_books.json libro {index}: campo no permitido {extra}")
                elif map_book(book) != book:
                    fields = sorted(k for k in BOOK_FIELDS if map_book(book).get(k) != book.get(k))
                    found.append(f"_books.json libro {index}: valor fuera de formato en {fields}")
            rebuilt_books = [map_book(b) for b in parsed]
            if text != _books_text(rebuilt_books):
                found.append("_books.json: texto distinto del que genera factory")
            books = rebuilt_books
    expected = {"AGENTS.md": AGENTS_GUIDE, ".gitignore": GITIGNORE}
    if books is not None:
        expected["llms.txt"] = _llms(books)
    for name, text in expected.items():
        path = map_dir / name
        if path.is_file() and path.read_text(encoding="utf-8") != text:
            found.append(f"{name}: contenido distinto del que genera factory")
    meta = map_dir / "_map.json"
    if meta.is_file():
        try:
            sha = str(json.loads(meta.read_text(encoding="utf-8")).get("source_catalog_sha256"))
        except (json.JSONDecodeError, AttributeError):
            sha = ""
        canonical = _meta_text(sha, notes, len(books or []))
        if not SHA_RE.fullmatch(sha) or meta.read_text(encoding="utf-8") != canonical:
            found.append("_map.json: contenido distinto del que genera factory")
    return found
