from __future__ import annotations

from backend.market.models import Quote


class QuoteValidator:
    """Valida se uma cotação pode participar da inteligência de mercado."""

    def is_valid(self, quote: Quote) -> bool:
        return (
            quote.status == "ok"
            and quote.price is not None
            and quote.currency is not None
        )
