import json
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from backend.canonical_portfolio import (
    serialize_portfolio_position,
    serialize_portfolio_positions,
)
from backend.models import PortfolioOwner, PortfolioPosition


def position(**changes: object) -> PortfolioPosition:
    values = {
        "institution": "UBS",
        "owner": PortfolioOwner.JOLIKA,
        "account": "ACC-1",
        "asset_class": "Equities",
        "asset_subclass": "Technology",
        "asset_name": "ARGOS Asset",
        "identifier": "ARGOS1",
        "identifier_type": "TICKER",
        "quantity": Decimal("100"),
        "unit_price": Decimal("152.4300"),
        "market_value": Decimal("15243.0000"),
        "currency": "USD",
        "portfolio_weight": Decimal("0.051200"),
        "reference_date": date(2026, 7, 30),
        "source_file": "portfolio.csv",
    }
    values.update(changes)
    return PortfolioPosition(**values)  # type: ignore[arg-type]


def test_serializes_exact_public_position_contract() -> None:
    assert serialize_portfolio_position(position()) == {
        "institution": "UBS",
        "owner": "JOLIKA",
        "account": "ACC-1",
        "asset_class": "Equities",
        "asset_subclass": "Technology",
        "asset_name": "ARGOS Asset",
        "identifier": "ARGOS1",
        "identifier_type": "TICKER",
        "quantity": "100",
        "unit_price": "152.4300",
        "market_value": "15243.0000",
        "currency": "USD",
        "portfolio_weight": "0.051200",
        "reference_date": "2026-07-30",
        "source_file": "portfolio.csv",
    }


def test_preserves_optional_nulls() -> None:
    payload = serialize_portfolio_position(position(
        account=None, asset_class=None, asset_subclass=None, asset_name=None,
        identifier=None, identifier_type=None, quantity=None, unit_price=None,
        market_value=None, currency=None, portfolio_weight=None,
        reference_date=None,
    ))
    assert all(payload[field] is None for field in (
        "account", "asset_class", "asset_subclass", "asset_name", "identifier",
        "identifier_type", "quantity", "unit_price", "market_value", "currency",
        "portfolio_weight", "reference_date",
    ))


def test_serializes_empty_collection_deterministically() -> None:
    assert serialize_portfolio_positions(()) == []
    positions = (position(), position(institution="Santander", source_file="san.xlsx"))
    assert json.dumps(serialize_portfolio_positions(positions)) == json.dumps(
        serialize_portfolio_positions(positions)
    )


def test_serialization_does_not_modify_frozen_position() -> None:
    original = position()
    before = repr(original)
    serialize_portfolio_position(original)
    assert repr(original) == before
    with pytest.raises(FrozenInstanceError):
        original.institution = "changed"  # type: ignore[misc]


def test_rejects_non_position_input() -> None:
    with pytest.raises(TypeError, match="PortfolioPosition"):
        serialize_portfolio_position(object())  # type: ignore[arg-type]
