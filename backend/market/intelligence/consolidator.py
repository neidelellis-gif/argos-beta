from __future__ import annotations

from backend.market.models import Quote


class MarketConsolidator:
    """Consolida resultados de múltiplas fontes."""

    def consolidate(self, quotes: list[Quote]) -> Quote:
        if not quotes:
            raise ValueError("Nenhuma cotação disponível para consolidação.")

        # MVP: utiliza a primeira cotação válida.
        # Nas próximas etapas serão adicionadas regras de consenso,
        # divergência entre provedores e detecção de outliers.
        return quotes[0]
