"""Catálogos de los cerebros (`_catalog.jsonl`): una entrada por nota, con caché por proceso."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PRINCIPAL = "principal"
DIARIO = "diario"
_CACHE: dict[tuple[str, int, int], list] = {}


@dataclass
class Entry:
    brain: str
    path: str  # relativa al cerebro
    abs_path: Path
    title: str
    keywords: list[str] = field(default_factory=list)
    abstract: str = ""
    section_path: list[str] = field(default_factory=list)
    tokens: int = 0
    book_id: str = ""
    book: str = ""
    chapter: str | None = None
    chapter_title: str | None = None
    pages: list[int] = field(default_factory=list)
    date: str = ""
    source: str = ""
    type: str = ""

    def citation(self) -> str:
        if self.brain == DIARIO:
            return f"Cerebro diario · {self.date or '—'} · {self.source or 'manual'}"
        parts = [self.book or self.book_id or "Libro"]
        if self.chapter:
            parts.append(f"cap. {self.chapter}")
        elif self.chapter_title:
            parts.append(self.chapter_title)
        if len(self.pages) == 2:
            first, last = self.pages
            parts.append(f"p. {first}" if first == last else f"pp. {first}–{last}")
        return " · ".join(parts)


def book_titles(directory: Path) -> dict[str, str]:
    """`_books.json` real (lista con `slug`/`title`) o diccionario `{id: {title}}`."""
    path = directory / "_books.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {
            str(b.get("slug") or b.get("id")): str(b.get("title", ""))
            for b in data
            if isinstance(b, dict)
        }
    if isinstance(data, dict):
        return {
            str(k): str((v or {}).get("title", "")) for k, v in data.items() if isinstance(v, dict)
        }
    return {}


def load(directory: Path, brain: str) -> list[Entry]:
    catalog = directory / "_catalog.jsonl"
    if not catalog.is_file():
        return []
    stat = catalog.stat()
    key = (str(catalog), stat.st_mtime_ns, stat.st_size)
    if key in _CACHE:
        return _CACHE[key]
    titles = book_titles(directory) if brain == PRINCIPAL else {}
    entries = []
    for line in catalog.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        entries.append(
            Entry(
                brain=brain,
                path=raw["path"],
                abs_path=directory / raw["path"],
                title=str(raw.get("title") or raw["path"]),
                keywords=list(raw.get("keywords") or []),
                abstract=str(raw.get("abstract") or ""),
                section_path=list(raw.get("section_path") or []),
                tokens=int(raw.get("tokens") or 0),
                book_id=str(raw.get("book_id") or ""),
                book=str(raw.get("book") or titles.get(str(raw.get("book_id")), "")),
                chapter=None if raw.get("chapter") is None else str(raw.get("chapter")),
                chapter_title=(
                    None if raw.get("chapter_title") is None else str(raw.get("chapter_title"))
                ),
                pages=list(raw.get("pages") or []),
                date=str(raw.get("date") or ""),
                source=str(raw.get("source") or ""),
                type=str(raw.get("type") or ""),
            )
        )
    _CACHE[key] = entries
    return entries


def note_body(entry: Entry) -> str:
    """Cuerpo de la nota sin frontmatter."""
    text = entry.abs_path.read_text(encoding="utf-8") if entry.abs_path.is_file() else ""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()
