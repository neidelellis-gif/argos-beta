from __future__ import annotations

from .market_connector import MarketConnector
from .models import MarketIntelligence


class MarketIntelligenceService:
    """Camada de Inteligência de Mercado do ARGOS."""

    def __init__(self, connector: MarketConnector):
        self._connector = connector

    def get_market_intelligence(self, ticker: str) -> MarketIntelligence:
        quote = self._connector.get_quote(ticker)

        return MarketIntelligence(
            quote=quote,
            confidence=1.0,
            sources_consulted=1,
            sources_confirmed=1,
            quality_status="validated",
            decision_note="Dados validados para o MVP.",
        )
