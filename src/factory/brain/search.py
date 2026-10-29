"""Búsqueda por palabras clave en los cerebros (sin dependencias ni embeddings; diseño D3)."""

from __future__ import annotations

from dataclasses import dataclass

from factory.brain import catalog
from factory.brain.catalog import DIARIO, PRINCIPAL, Entry
from factory.brain.text import fold, terms
from factory.config import Config

WEIGHTS = {"title": 3, "keywords": 3, "section": 2, "abstract": 1, "book": 1}
PHRASE_BONUS = 2


@dataclass
class Hit:
    entry: Entry
    score: float


def _field_terms(text: str) -> set[str]:
    found = set()
    for term in terms(text):
        found.add(term)
        found.update(part for part in term.replace("_", "-").split("-") if len(part) > 2)
    return found


def score(entry: Entry, query_terms: list[str], phrase: str) -> float:
    fields = {
        "title": _field_terms(entry.title),
        "keywords": _field_terms(" ".join(entry.keywords)),
        "section": _field_terms(" ".join(entry.section_path)),
        "abstract": _field_terms(entry.abstract),
        "book": _field_terms(f"{entry.book} {entry.book_id}"),
    }
    unique = list(dict.fromkeys(query_terms))
    total = sum(WEIGHTS[name] for term in unique for name, words in fields.items() if term in words)
    if not total:
        return 0
    if phrase and (phrase in fold(entry.title) or phrase in fold(entry.abstract)):
        total += PHRASE_BONUS
    # cobertura: una nota con todos los términos de la consulta gana a una que solo tiene alguno
    matched = sum(1 for term in unique if any(term in words for words in fields.values()))
    return round(total * matched / len(unique), 2)


def brains(config: Config, which: str = "all") -> list[tuple[str, list[Entry]]]:
    selected = []
    if which in ("all", PRINCIPAL):
        selected.append((PRINCIPAL, catalog.load(config.principal_path, PRINCIPAL)))
    if which in ("all", DIARIO):
        selected.append((DIARIO, catalog.load(config.daily_path, DIARIO)))
    return selected


def search(config: Config, query: str, which: str = "all", limit: int | None = None) -> list[Hit]:
    query_terms = terms(query)
    if not query_terms:
        return []
    phrase = " ".join(query_terms)
    hits = []
    for _name, entries in brains(config, which):
        for entry in entries:
            value = score(entry, query_terms, phrase)
            if value > 0:
                hits.append(Hit(entry, value))
    hits.sort(key=lambda h: (-h.score, h.entry.tokens, h.entry.path))
    return hits[: limit or config.brain.search_limit]
