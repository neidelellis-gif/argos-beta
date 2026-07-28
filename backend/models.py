"""Core domain models shared across ARGOS layers."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class PortfolioPosition:
    """Universal representation of a portfolio position in ARGOS."""

    institution: str
    account: str
    asset_class: str
    asset_subclass: Optional[str]
    asset_name: str
    identifier: Optional[str]
    identifier_type: Optional[str]
    quantity: Optional[Decimal]
    unit_price: Optional[Decimal]
    market_value: Decimal
    currency: str
    portfolio_weight: Optional[Decimal]
    reference_date: date
    source_file: str
