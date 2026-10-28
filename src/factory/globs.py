"""Globs de rutas relativas al repo: `**` (cualquier profundidad), `*` y `?` sin cruzar `/`."""

from __future__ import annotations

import re


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Glob con `**` (cualquier profundidad), `*` y `?` (sin cruzar `/`). Anclado a la raíz."""
    pattern = pattern.strip().removeprefix("./")
    if pattern.endswith("/"):
        pattern += "**"
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
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
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, patterns: list[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)
