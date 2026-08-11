from dataclasses import replace
from decimal import Decimal

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_diagnostics import (
    diagnose_consolidated,
    diagnose_institution,
)


def position(
    institution: str = "UBS",
    symbol: str | None = "AAA",
    value: str | None = "100",
    currency: str = "USD",
    weight: str | None = "0.5",
    owner: PortfolioOwner = PortfolioOwner.JOLIKA,
    economic_class: EconomicAssetClass | None = EconomicAssetClass.EQUITIES,
    asset_class: str | None = None,
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=None,
        asset_class=asset_class,
        asset_subclass=None,
        asset_name=symbol or "Asset without symbol",
        identifier=symbol,
        identifier_type="ticker" if symbol else None,
        quantity=None,
        unit_price=None,
        market_value=None if value is None else Decimal(value),
        currency=currency,
        portfolio_weight=None if weight is None else Decimal(weight),
        reference_date=None,
        source_file=f"{institution}.csv",
        economic_asset_class=economic_class,
    )


def test_empty_portfolio_has_empty_diagnostics():
    institution = diagnose_institution([])
    consolidated = diagnose_consolidated([])

    assert institution.institution is None
    assert institution.position_count == 0
    assert institution.data_quality_warnings == ()
    assert consolidated.institutions == ()
    assert consolidated.total_positions == 0
    assert consolidated.totals_by_currency == {}
    assert institution.economic_allocation_by_currency == {}
    assert consolidated.economic_allocation_by_currency == {}


def test_diagnoses_one_institution_and_multiple_currencies():
    result = diagnose_institution(
        [position(value="100"), position(symbol="BBB", value="40", currency="EUR")]
    )

    assert result.institution == "UBS"
    assert result.position_count == 2
    assert result.currencies == ("EUR", "USD")
    assert result.market_value_by_currency == {
        "USD": Decimal("100"),
        "EUR": Decimal("40"),
    }
    assert result.total_weight_by_currency == {
        "USD": Decimal("0.5"),
        "EUR": Decimal("0.5"),
    }


def test_reports_missing_fields_and_duplicates():
    result = diagnose_institution(
        [
            position(symbol="AAA"),
            position(symbol="aaa", value="20"),
            position(symbol=None),
            position(symbol="BBB", value=None),
        ]
    )

    assert result.duplicate_assets == {"AAA": 2}
    assert result.assets_without_symbol == ("Asset without symbol",)
    assert result.assets_without_market_value == ("BBB",)
    assert len(result.data_quality_warnings) == 3


def test_rejects_mixed_institutions_in_individual_diagnostic():
    with pytest.raises(ValueError, match="only one institution"):
        diagnose_institution([position(), position(institution="Santander")])


def test_consolidates_only_individual_results_and_finds_shared_assets():
    ubs = diagnose_institution([position(), position(symbol="BBB", value="20")])
    santander = diagnose_institution(
        [
            position(institution="Santander", symbol="AAA", value="30"),
            position(
                institution="Santander",
                symbol="CCC",
                value="50",
                currency="BRL",
            ),
        ]
    )

    result = diagnose_consolidated([ubs, santander])

    assert result.institutions == ("Santander", "UBS")
    assert result.total_positions == 4
    assert result.totals_by_currency == {
        "USD": Decimal("150"),
        "BRL": Decimal("50"),
    }
    assert result.unique_asset_count == 3
    assert result.repeated_asset_count == 1


def test_preserves_original_objects_and_input_list():
    positions = [position()]
    original = replace(positions[0])

    diagnose_institution(positions)

    assert positions == [original]
    assert positions[0] is not original


def cash_position(account: str, value: str, currency: str = "USD"):
    return PortfolioPosition(
        institution="Santander",
        owner=PortfolioOwner.JOLIKA,
        account=account,
        asset_class="Caixa",
        asset_subclass=None,
        asset_name="DDA CUSTODIAL CASH ACCOUNTS",
        identifier="DDA CUSTODIAL CASH ACCOUNTS",
        identifier_type=None,
        quantity=None,
        unit_price=None,
        market_value=Decimal(value),
        currency=currency,
        portfolio_weight=None,
        reference_date=None,
        source_file="santander.xlsx",
        economic_asset_class=EconomicAssetClass.CASH,
    )


def test_distinct_cash_accounts_with_same_textual_identifier_are_not_duplicates():
    result = diagnose_institution(
        [
            cash_position("115099244", "0", "USD"),
            cash_position("115111355", "75226.16", "USD"),
            cash_position("115111444", "22857.13", "USD"),
            cash_position("115088644", "350", "USD"),
        ]
    )

    assert result.duplicate_assets == {}
    assert "1 duplicated asset(s)" not in result.data_quality_warnings


def test_identical_cash_account_rows_are_still_duplicates():
    result = diagnose_institution(
        [
            cash_position("115111355", "75226.16", "USD"),
            cash_position("115111355", "75226.16", "USD"),
        ]
    )

    assert result.duplicate_assets == {
        "SANTANDER|115111355|USD|DDA CUSTODIAL CASH ACCOUNTS": 2
    }
    assert "1 duplicated asset(s)" in result.data_quality_warnings


def test_cash_prefers_economic_class_over_legacy_asset_class():
    result = diagnose_institution(
        [
            position(
                symbol="CASH",
                asset_class="Santander Liquidity",
                economic_class=EconomicAssetClass.CASH,
            ),
            position(
                symbol="CASH",
                asset_class="Santander Liquidity",
                economic_class=EconomicAssetClass.CASH,
            ),
        ]
    )

    assert "UBS||USD|CASH" in result.duplicate_assets


def test_cash_legacy_fallback_applies_without_economic_class():
    result = diagnose_institution(
        [position(symbol="CASH", economic_class=None, asset_class="CAIXA")]
    )

    assert result.asset_symbols == ("UBS||USD|CASH",)


def test_aggregates_economic_values_by_currency_without_cross_currency_total():
    result = diagnose_institution(
        [
            position(value="100", economic_class=EconomicAssetClass.CASH),
            position(symbol="BOND", value="250", economic_class=EconomicAssetClass.FIXED_INCOME),
            position(symbol="EUR-CASH", value="40", currency="EUR", economic_class=EconomicAssetClass.CASH),
        ]
    )

    assert result.economic_allocation_by_currency == {
        "USD": {
            EconomicAssetClass.CASH: Decimal("100"),
            EconomicAssetClass.FIXED_INCOME: Decimal("250"),
        },
        "EUR": {EconomicAssetClass.CASH: Decimal("40")},
    }


def test_warns_once_per_jolika_institution_for_missing_economic_classes():
    result = diagnose_institution(
        [position(economic_class=None), position(symbol="BBB", economic_class=None)]
    )

    assert result.data_quality_warnings == (
        "2 JOLIKA position(s) without economic asset class",
    )


def test_does_not_warn_nei_about_missing_economic_class():
    result = diagnose_institution(
        [position(owner=PortfolioOwner.NEI, economic_class=None)]
    )

    assert result.data_quality_warnings == ()


def test_consolidated_economic_allocation_sums_only_institution_diagnostics():
    ubs = diagnose_institution(
        [position(value="100", economic_class=EconomicAssetClass.CASH)]
    )
    santander = diagnose_institution(
        [
            position(institution="Santander", value="50", economic_class=EconomicAssetClass.CASH),
            position(institution="Santander", symbol="BOND", value="20", currency="EUR", economic_class=EconomicAssetClass.FIXED_INCOME),
        ]
    )

    result = diagnose_consolidated([ubs, santander])

    assert result.institutions == ("Santander", "UBS")
    assert result.economic_allocation_by_currency == {
        "USD": {EconomicAssetClass.CASH: Decimal("150")},
        "EUR": {EconomicAssetClass.FIXED_INCOME: Decimal("20")},
    }


def test_consolidated_warnings_keep_institution_identity():
    ubs = diagnose_institution([position(economic_class=None)])
    result = diagnose_consolidated([ubs])

    assert result.consolidated_warnings == (
        "UBS: 1 JOLIKA position(s) without economic asset class",
    )
