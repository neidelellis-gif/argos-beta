from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Quote


class MarketProvider(ABC):
    """Contract that every external market-data provider must implement."""

    name: str = "provider"

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote:
        """Return a normalized Quote for a ticker or an unavailable Quote."""
        raise NotImplementedError
