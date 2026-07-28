"""Basic consolidation for positions already normalized to the MPU."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, Tuple

from backend.models import PortfolioPosition


@dataclass(frozen=True)
class PortfolioConsolidation:
    """Institution views followed by a distinct, currency-safe total view."""

    positions_by_institution: Dict[str, Tuple[PortfolioPosition, ...]]
    consolidated_positions: Tuple[PortfolioPosition, ...]
    totals_by_currency: Dict[str, Decimal]


def consolidate_portfolio_positions(
    positions: Iterable[PortfolioPosition],
) -> PortfolioConsolidation:
    """Group positions by institution and build a separate consolidated view."""
    original_positions = tuple(positions)
    grouped = {}
    for position in original_positions:
        grouped.setdefault(position.institution, []).append(position)

    positions_by_institution = {
        institution: tuple(institution_positions)
        for institution, institution_positions in grouped.items()
    }

    totals_by_currency = {}
    for position in original_positions:
        if position.currency is None or position.market_value is None:
            continue
        totals_by_currency[position.currency] = (
            totals_by_currency.get(position.currency, Decimal("0"))
            + position.market_value
        )

    return PortfolioConsolidation(
        positions_by_institution=positions_by_institution,
        consolidated_positions=tuple(original_positions),
        totals_by_currency=totals_by_currency,
    )
