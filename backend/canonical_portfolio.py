"""Public serialization for canonical portfolio positions."""

from collections.abc import Iterable
from decimal import Decimal
from typing import TypeAlias

from backend.models import PortfolioPosition


CanonicalPositionPayload: TypeAlias = dict[str, str | None]


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def serialize_portfolio_position(
    position: PortfolioPosition,
) -> CanonicalPositionPayload:
    """Serialize one validated position without changing or enriching it."""
    if not isinstance(position, PortfolioPosition):
        raise TypeError("position must be a PortfolioPosition")
    return {
        "institution": position.institution,
        "owner": position.owner.value,
        "account": position.account,
        "asset_class": position.asset_class,
        "asset_subclass": position.asset_subclass,
        "asset_name": position.asset_name,
        "identifier": position.identifier,
        "identifier_type": position.identifier_type,
        "quantity": _decimal(position.quantity),
        "unit_price": _decimal(position.unit_price),
        "market_value": _decimal(position.market_value),
        "currency": position.currency,
        "portfolio_weight": _decimal(position.portfolio_weight),
        "reference_date": (
            None if position.reference_date is None
            else position.reference_date.isoformat()
        ),
        "source_file": position.source_file,
    }


def serialize_portfolio_positions(
    positions: Iterable[PortfolioPosition],
) -> list[CanonicalPositionPayload]:
    """Serialize canonical positions while preserving their official order."""
    return [serialize_portfolio_position(position) for position in positions]
