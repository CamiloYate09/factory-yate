"""El equipo ideal: plantilla en el frontmatter de `.claude/agents/*.md` (`roster`) y
convocatoria determinista a partir de los cambios y de la petición (`lineup`).
Ver docs/harness/equipo.md."""

from __future__ import annotations


class TeamError(Exception):
    """Error de uso de `factory team`: referencia git inválida, repo sin git o petición ilegible."""
