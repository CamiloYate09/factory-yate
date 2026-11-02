"""Precios por modelo para el backend Strands, que solo informa de tokens (diseño D4).

Sin precio no hay coste, y sin coste el presupuesto y los cortacircuitos dejarían de funcionar
en silencio: por eso un modelo sin precio hace fallar la invocación en lugar de costar 0.
"""

from __future__ import annotations

from dataclasses import dataclass

# USD por millón de tokens, API de Anthropic. La escritura en caché es la de TTL de 5 minutos
# (1,25 × entrada). Haiku 5.5 usa el tramo de prompts > 100K: el uso de Strands es agregado y no
# permite saber el tamaño de cada petición, así que se elige el tramo que nunca subestima.
PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICES_DATE = "2026-10-06"
CACHE_WRITE_FACTOR = 1.25


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_read: float
    cache_write: float

    @property
    def max_per_token(self) -> float:
        """El precio más alto por token: base de la cota conservadora del presupuesto (D7)."""
        return max(self.input, self.output, self.cache_read, self.cache_write) / 1_000_000


DEFAULT_PRICES: dict[str, ModelPrice] = {
    "anthropic/claude-opus-5-5": ModelPrice(4.00, 20.00, 0.20, 5.00),
    "anthropic/claude-sonnet-5-5": ModelPrice(2.00, 10.00, 0.20, 2.50),
    "anthropic/claude-haiku-5-5": ModelPrice(0.50, 2.50, 0.05, 0.625),
}


def cost_usd(
    price: ModelPrice,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Coste de una invocación; `input_tokens` excluye los tokens leídos o escritos en caché."""
    total = (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_read_tokens * price.cache_read
        + cache_write_tokens * price.cache_write
    )
    return total / 1_000_000


def missing_price_hint(model: str) -> str:
    return (
        f"El modelo '{model}' no tiene precio: añade [agent.strands.prices.\"{model}\"] con "
        "input y output (USD por millón de tokens) en factory.toml."
    )
