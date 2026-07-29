from dataclasses import replace
from decimal import Decimal

from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_consolidation import consolidate_portfolio_positions


def position(institution, value, currency="USD"):
    return PortfolioPosition(
        institution=institution,
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name=institution,
        identifier=None,
        identifier_type=None,
        quantity=None,
        unit_price=None,
        market_value=Decimal(value),
        currency=currency,
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )


def test_separates_positions_by_institution_before_consolidating():
    positions = [
        position("Santander", "10"),
        position("UBS", "20"),
        position("TipRanks", "30"),
    ]

    result = consolidate_portfolio_positions(positions)

    assert set(result.positions_by_institution) == {
        "Santander",
        "UBS",
        "TipRanks",
    }
    assert result.positions_by_institution["UBS"] == (positions[1],)


def test_keeps_consolidated_positions_in_a_separate_view():
    positions = [position("Santander", "10"), position("UBS", "20")]

    result = consolidate_portfolio_positions(positions)

    assert result.consolidated_positions == tuple(positions)
    assert all(
        position.owner is PortfolioOwner.JOLIKA
        for position in result.consolidated_positions
    )
    assert (
        result.consolidated_positions
        is not result.positions_by_institution["UBS"]
    )


def test_preserves_original_positions_and_input_list():
    positions = [position("UBS", "20")]
    original_position = replace(positions[0])

    consolidate_portfolio_positions(positions)

    assert positions == [original_position]
    assert positions[0] == original_position


def test_totals_different_currencies_separately():
    positions = [position("UBS", "20", "USD"), position("Santander", "30", "EUR")]

    result = consolidate_portfolio_positions(positions)

    assert result.totals_by_currency == {
        "USD": Decimal("20"),
        "EUR": Decimal("30"),
    }


def test_consolidates_values_only_within_the_same_currency():
    positions = [position("UBS", "20"), position("Santander", "30")]

    result = consolidate_portfolio_positions(positions)

    assert result.totals_by_currency == {"USD": Decimal("50")}


def test_returns_empty_views_for_an_empty_list():
    result = consolidate_portfolio_positions([])

    assert result.positions_by_institution == {}
    assert result.consolidated_positions == ()
    assert result.totals_by_currency == {}
