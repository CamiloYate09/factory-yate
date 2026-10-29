"""Utilidades de texto deterministas para los cerebros (sin modelos ni dependencias)."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

STOPWORDS = frozenset(
    """
    a al algo algunas algunos ante antes como con contra cual cuando de del desde donde dos el
    ella ellas ellos en entre era es esa ese eso esta este esto estos fue ha hay la las le les lo
    los mas me mi mientras muy nada ni no nos o otra otro para pero poco por porque que quien se
    sea ser si sin sobre solo son su sus tambien te tiene todo todos tras tu un una uno unos y ya
    usar uso
    a about after all also an and any are as at be because been but by can could did do does
    for from had has have how i if in into is it its may more most must no not of on or other
    our out over should so such than that the their them then there these they this those to
    under up use used using was we were what when where which while who will with would you your
    """.split()
)
WORD_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
ABSTRACT_MAX = 300


def fold(text: str) -> str:
    """Minúsculas y sin acentos: `Añadí` → `anadi`."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def terms(text: str) -> list[str]:
    """Términos significativos (sin palabras vacías ni números sueltos)."""
    return [
        word
        for word in WORD_RE.findall(fold(text))
        if word not in STOPWORDS and len(word) > 2 and not word.isdigit()
    ]


def keywords(text: str, limit: int = 8) -> list[str]:
    counts = Counter(terms(text))
    return [word for word, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def abstract(text: str) -> str:
    plain = " ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    plain = re.sub(r"^#+\s*", "", plain)
    first = SENTENCE_RE.split(plain, maxsplit=1)[0] if plain else ""
    return first if len(first) <= ABSTRACT_MAX else first[: ABSTRACT_MAX - 1].rstrip() + "…"


def estimate_tokens(text: str) -> int:
    """Misma estimación que el vault principal: caracteres / 4."""
    return max(1, len(text) // 4)
