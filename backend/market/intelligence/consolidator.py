from __future__ import annotations

from backend.market.intelligence.validators.quote_validator import QuoteValidator
from backend.market.models import Quote


class MarketConsolidator:
    """Consolida resultados de múltiplas fontes."""

    def __init__(self) -> None:
        self._validator = QuoteValidator()

    def consolidate(self, quotes: list[Quote]) -> Quote:
        if not quotes:
            raise ValueError("Nenhuma cotação disponível para consolidação.")

        for quote in quotes:
            if self._validator.is_valid(quote):
                return quote

        raise ValueError("Nenhuma cotação válida disponível para consolidação.")