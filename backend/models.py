"""Core domain models shared across ARGOS layers."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class PortfolioOwner(str, Enum):
    """Official owners supported by the ARGOS portfolio domain.

    Future Bradesco, Ágora, Monte Bravo and crypto connectors must assign the
    appropriate owner through this same field rather than creating a parallel
    ownership concept.
    """

    JOLIKA = "JOLIKA"
    NEI = "NEI"


@dataclass(frozen=True)
class PortfolioPosition:
    """Universal representation of a portfolio position in ARGOS."""

    institution: str
    owner: PortfolioOwner
    account: Optional[str]
    asset_class: Optional[str]
    asset_subclass: Optional[str]
    asset_name: Optional[str]
    identifier: Optional[str]
    identifier_type: Optional[str]
    quantity: Optional[Decimal]
    unit_price: Optional[Decimal]
    market_value: Optional[Decimal]
    currency: Optional[str]
    portfolio_weight: Optional[Decimal]
    reference_date: Optional[date]
    source_file: str

    def __post_init__(self):
        if not isinstance(self.owner, PortfolioOwner):
            raise ValueError("owner must be JOLIKA or NEI")
