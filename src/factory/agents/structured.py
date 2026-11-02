"""Extracción de la salida estructurada de un agente, común a todos los backends (diseño D8).

La validación contra el esquema la hace después `schemas.py`; aquí solo se localiza el objeto.
"""

from __future__ import annotations

import json
import re
from typing import Any

FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def structured_output(data: dict[str, Any]) -> dict[str, Any] | None:
    """Salida validada por --json-schema: campo estructurado o, en su defecto, JSON en `result`."""
    for key in ("structured_output", "structuredOutput", "output"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    text = data.get("result")
    if not isinstance(text, str):
        return None
    candidates = [text.strip()]
    fenced = FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def from_text(text: str) -> dict[str, Any] | None:
    """Objeto JSON de una respuesta en texto libre (backends sin salida estructurada nativa).

    Además del bloque ```json y del texto completo, acepta un objeto precedido de prosa.
    """
    found = structured_output({"result": text})
    if found is not None:
        return found
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def schema_instruction(schema: dict[str, Any]) -> str:
    """Instrucción que se añade al prompt cuando el backend no valida el esquema por sí mismo."""
    return (
        "\n\n## Formato de la respuesta final\n"
        "Termina con un único objeto JSON que cumpla este esquema, sin texto después:\n"
        "```json\n" + json.dumps(schema, ensure_ascii=False, indent=2) + "\n```\n"
    )
