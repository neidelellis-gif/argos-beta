from dataclasses import replace
from decimal import Decimal

import pytest

from backend.models import PortfolioPosition
from backend.portfolio_diagnostics import (
    diagnose_consolidated,
    diagnose_institution,
)


def position(
    institution="UBS",
    symbol="AAA",
    value="100",
    currency="USD",
    weight="0.5",
):
    return PortfolioPosition(
        institution=institution,
        account=None,
        asset_class=None,
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
