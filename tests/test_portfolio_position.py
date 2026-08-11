from dataclasses import fields
from collections.abc import Callable
from typing import cast

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


def _unchecked_position(**position_fields: object) -> PortfolioPosition:
    """Call the constructor with intentionally invalid runtime arguments."""
    constructor = cast(Callable[..., PortfolioPosition], PortfolioPosition)
    return constructor(**position_fields)


def test_portfolio_position_has_mpu_fields_and_optional_economic_class_at_end():
    assert [field.name for field in fields(PortfolioPosition)] == [
        "institution",
        "owner",
        "account",
        "asset_class",
        "asset_subclass",
        "asset_name",
        "identifier",
        "identifier_type",
        "quantity",
        "unit_price",
        "market_value",
        "currency",
        "portfolio_weight",
        "reference_date",
        "source_file",
        "economic_asset_class",
    ]


def test_economic_asset_class_has_only_the_jolika_phase_one_taxonomy():
    assert {item.value for item in EconomicAssetClass} == {
        "Caixa",
        "Renda Fixa",
        "Ações",
        "ETFs de Ações",
        "Ouro & Commodities",
        "Criptoativos",
        "Alternativos / Private Markets",
        "Fundos / Estratégias",
    }


def test_portfolio_owner_has_only_the_official_owners():
    assert set(PortfolioOwner) == {PortfolioOwner.JOLIKA, PortfolioOwner.NEI}


def test_portfolio_position_requires_owner():
    with pytest.raises(TypeError, match="owner"):
        _unchecked_position(
            institution="UBS",
            account=None,
            asset_class=None,
            asset_subclass=None,
            asset_name=None,
            identifier=None,
            identifier_type=None,
            quantity=None,
            unit_price=None,
            market_value=None,
            currency=None,
            portfolio_weight=None,
            reference_date=None,
            source_file="ubs.csv",
        )


def test_portfolio_position_rejects_an_invalid_owner():
    with pytest.raises(ValueError, match="owner must be JOLIKA or NEI"):
        _unchecked_position(
            institution="UBS",
            owner=None,
            account=None,
            asset_class=None,
            asset_subclass=None,
            asset_name=None,
            identifier=None,
            identifier_type=None,
            quantity=None,
            unit_price=None,
            market_value=None,
            currency=None,
            portfolio_weight=None,
            reference_date=None,
            source_file="ubs.csv",
        )
