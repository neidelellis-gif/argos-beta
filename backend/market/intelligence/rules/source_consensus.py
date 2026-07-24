from __future__ import annotations

from backend.market.models import Quote


class SourceConsensusRule:
    """Regra simples de consenso entre fontes."""

    def evaluate(self, quotes: list[Quote]) -> bool:
        return len(quotes) >= 2
