"""Bridge UBS portfolio intelligence into the ARGOS daily flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.market.market_connector import MarketConnector
from backend.models import PortfolioOwner, PortfolioPosition
from backend.ubs_operational_intelligence import (
    UBSOperationalIntelligence,
    build_ubs_operational_intelligence,
)
from backend.ubs_portfolio_intelligence import (
    UBSPortfolioIntelligence,
    build_ubs_portfolio_intelligence,
)
from backend.ubs_quantitative_intelligence import (
    UBSQuantitativeIntelligence,
    build_ubs_quantitative_intelligence,
)


@dataclass(frozen=True)
class UBSDailyIntelligence:
    """Complete UBS intelligence package available to the daily flow."""

    structural: UBSPortfolioIntelligence
    quantitative: UBSQuantitativeIntelligence
    operational: UBSOperationalIntelligence

    def to_dict(self) -> dict[str, object]:
        """Return the public UBS intelligence payload for the daily experience."""

        structural = self.structural
        quantitative = self.quantitative
        operational = self.operational

        return {
            "institution": structural.institution,
            "owner": structural.owner.value,
            "position_count": structural.position_count,
            "overall_level": operational.overall_level,
            "structural_level": operational.structural_level,
            "quantitative_level": operational.quantitative_level,
            "executive_reading": operational.executive_reading,
            "quantitative_coverage": {
                "lookback_days": quantitative.lookback_days,
                "total_positions": quantitative.position_count,
                "analyzed_positions": quantitative.analyzed_position_count,
                "unavailable_positions": quantitative.unavailable_position_count,
            },
        }


class UBSDailyIntelligenceService:
    """Build UBS/JOLIKA intelligence without changing daily engine contracts."""

    def __init__(
        self,
        market_connector: MarketConnector,
        *,
        history_days: int = 252,
    ) -> None:
        if not isinstance(market_connector, MarketConnector):
            raise TypeError(
                "market_connector must be a MarketConnector"
            )

        if (
            isinstance(history_days, bool)
            or not isinstance(history_days, int)
            or history_days <= 0
        ):
            raise ValueError(
                "history_days must be a positive integer"
            )

        self._market_connector = market_connector
        self._history_days = history_days

    @staticmethod
    def _ubs_positions(
        positions: Iterable[PortfolioPosition],
    ) -> tuple[PortfolioPosition, ...]:
        items = tuple(positions)

        if any(
            not isinstance(position, PortfolioPosition)
            for position in items
        ):
            raise TypeError(
                "positions accepts only PortfolioPosition instances"
            )

        return tuple(
            position
            for position in items
            if (
                position.owner is PortfolioOwner.JOLIKA
                and position.institution == "UBS"
            )
        )

    def build(
        self,
        positions: Iterable[PortfolioPosition],
    ) -> UBSDailyIntelligence | None:
        """Return UBS intelligence, or None when UBS is absent."""

        ubs_positions = self._ubs_positions(positions)

        if not ubs_positions:
            return None

        structural = build_ubs_portfolio_intelligence(
            ubs_positions
        )

        quantitative = build_ubs_quantitative_intelligence(
            ubs_positions,
            market_connector=self._market_connector,
            lookback_days=self._history_days,
        )

        operational = build_ubs_operational_intelligence(
            structural,
            quantitative,
        )

        return UBSDailyIntelligence(
            structural=structural,
            quantitative=quantitative,
            operational=operational,
        )
