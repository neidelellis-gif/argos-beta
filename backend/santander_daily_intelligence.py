"""Bridge Santander portfolio intelligence into the ARGOS daily flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.institution_patrimonial_report import build_institution_patrimonial_report
from backend.market.market_connector import MarketConnector
from backend.models import PortfolioOwner, PortfolioPosition
from backend.patrimonial_analysis_method import PatrimonialAnalysisReport
from backend.santander_operational_intelligence import (
    SantanderOperationalIntelligence,
    build_santander_operational_intelligence,
)
from backend.santander_portfolio_intelligence import (
    SantanderPortfolioIntelligence,
    build_santander_portfolio_intelligence,
)
from backend.santander_quantitative_intelligence import (
    SantanderQuantitativeIntelligence,
    build_santander_quantitative_intelligence,
)


@dataclass(frozen=True)
class SantanderDailyIntelligence:
    """Complete Santander intelligence package available to the daily flow."""

    structural: SantanderPortfolioIntelligence
    quantitative: SantanderQuantitativeIntelligence
    operational: SantanderOperationalIntelligence
    patrimonial_report: PatrimonialAnalysisReport

    def to_dict(self) -> dict[str, object]:
        """Return the public Santander intelligence payload for the daily experience."""

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
            "patrimonial_analysis": self.patrimonial_report.to_dict(),
        }


class SantanderDailyIntelligenceService:
    """Build Santander/JOLIKA intelligence without changing daily engine contracts."""

    def __init__(self, market_connector: MarketConnector, *, history_days: int = 252) -> None:
        if not isinstance(market_connector, MarketConnector):
            raise TypeError("market_connector must be a MarketConnector")
        if isinstance(history_days, bool) or not isinstance(history_days, int) or history_days <= 0:
            raise ValueError("history_days must be a positive integer")
        self._market_connector = market_connector
        self._history_days = history_days

    @staticmethod
    def _santander_positions(positions: Iterable[PortfolioPosition]) -> tuple[PortfolioPosition, ...]:
        items = tuple(positions)
        if any(not isinstance(position, PortfolioPosition) for position in items):
            raise TypeError("positions accepts only PortfolioPosition instances")
        return tuple(
            position
            for position in items
            if position.owner is PortfolioOwner.JOLIKA and position.institution == "Santander"
        )

    def build(self, positions: Iterable[PortfolioPosition]) -> SantanderDailyIntelligence | None:
        """Return Santander intelligence, or None when Santander is absent."""

        santander_positions = self._santander_positions(positions)
        if not santander_positions:
            return None

        structural = build_santander_portfolio_intelligence(santander_positions)
        quantitative = build_santander_quantitative_intelligence(
            santander_positions,
            market_connector=self._market_connector,
            lookback_days=self._history_days,
        )
        operational = build_santander_operational_intelligence(structural, quantitative)
        patrimonial_report = build_institution_patrimonial_report(
            structural,
            quantitative,
            operational,
        )

        return SantanderDailyIntelligence(
            structural=structural,
            quantitative=quantitative,
            operational=operational,
            patrimonial_report=patrimonial_report,
        )
