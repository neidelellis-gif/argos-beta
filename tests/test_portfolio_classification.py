from dataclasses import replace

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_classification import (
    classify_jolika_position,
    classify_jolika_positions,
)


def position(**changes) -> PortfolioPosition:
    base = PortfolioPosition(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name=None,
        identifier=None,
        identifier_type=None,
        quantity=None,
        unit_price=None,
        market_value=None,
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="positions.csv",
    )
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"identifier": "GLD"}, EconomicAssetClass.GOLD_AND_COMMODITIES),
        ({"asset_name": "SPDR GOLD TRUST"}, EconomicAssetClass.GOLD_AND_COMMODITIES),
        ({"identifier": "ARKB"}, EconomicAssetClass.CRYPTOASSETS),
        ({"identifier": "ETHB"}, EconomicAssetClass.CRYPTOASSETS),
        ({"identifier": "ARKQ"}, EconomicAssetClass.EQUITY_ETFS),
        ({"identifier": "JEPI"}, EconomicAssetClass.EQUITY_ETFS),
        ({"identifier": "SMH"}, EconomicAssetClass.EQUITY_ETFS),
        ({"asset_name": "ISHARES BITCOIN TRUST ETF"}, EconomicAssetClass.CRYPTOASSETS),
        (
            {"institution": "Santander", "asset_class": "ETF/Fundo", "asset_name": "iShares Core MSCI World ETF"},
            EconomicAssetClass.EQUITY_ETFS,
        ),
        ({"asset_name": "BNP PARIBAS T-IDN CO1 08/14/2026"}, EconomicAssetClass.FIXED_INCOME),
        ({"asset_class": "Caixa"}, EconomicAssetClass.CASH),
        ({"asset_class": "Renda Fixa"}, EconomicAssetClass.FIXED_INCOME),
        ({"asset_class": "Ação"}, EconomicAssetClass.EQUITIES),
        ({"asset_class": "Ações"}, EconomicAssetClass.EQUITIES),
        ({"asset_class": "Fundo"}, EconomicAssetClass.FUNDS_STRATEGIES),
        ({"asset_class": "Alternativos"}, EconomicAssetClass.ALTERNATIVES_PRIVATE_MARKETS),
    ],
)
def test_confirmed_phase_one_cases(changes, expected):
    assert classify_jolika_position(position(**changes)).economic_asset_class is expected


def test_identifier_precedes_original_class():
    result = classify_jolika_position(position(identifier="GLD", asset_class="Ação"))
    assert result.economic_asset_class is EconomicAssetClass.GOLD_AND_COMMODITIES


def test_known_name_precedes_original_fallback():
    result = classify_jolika_position(position(asset_name="SPDR GOLD TRUST", asset_class="Fundo"))
    assert result.economic_asset_class is EconomicAssetClass.GOLD_AND_COMMODITIES


@pytest.mark.parametrize(
    ("identifier", "name", "expected"),
    [
        ("ARKB", "ARK 21SHARES BITCOIN ETF", EconomicAssetClass.CRYPTOASSETS),
        ("GLD", "SPDR GOLD SHARES ETF", EconomicAssetClass.GOLD_AND_COMMODITIES),
    ],
)
def test_non_equity_etfs_do_not_become_equity_etfs(identifier, name, expected):
    result = classify_jolika_position(
        position(identifier=identifier, asset_name=name, asset_class="ETF/Fundo")
    )
    assert result.economic_asset_class is expected


def test_bond_note_pattern_does_not_remain_unknown():
    result = classify_jolika_position(position(asset_name="ACME SENIOR NOTE 5.5%"))
    assert result.economic_asset_class is EconomicAssetClass.FIXED_INCOME


def test_unknown_position_has_no_economic_classification():
    assert classify_jolika_position(position(asset_name="Unknown asset")).economic_asset_class is None


def test_classification_preserves_original_position_and_asset_class():
    original = position(identifier="GLD", asset_class="ETF/Fundo")
    result = classify_jolika_position(original)
    assert result is not original
    assert original.economic_asset_class is None
    assert result.asset_class == original.asset_class == "ETF/Fundo"


def test_classification_is_idempotent():
    once = classify_jolika_position(position(identifier="ETHB"))
    assert classify_jolika_position(once) == once


def test_nei_position_is_rejected():
    with pytest.raises(ValueError, match="non-JOLIKA"):
        classify_jolika_position(position(owner=PortfolioOwner.NEI))


def test_mixed_batch_is_rejected():
    with pytest.raises(ValueError, match="mixed or non-JOLIKA"):
        classify_jolika_positions((position(), position(owner=PortfolioOwner.NEI)))
