from dataclasses import replace
from decimal import Decimal

import pytest

from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_consolidation import (
    PortfolioConsolidationEngine,
    consolidate_portfolio_positions,
)


def position(institution, identifier, value="100", owner=None, **changes):
    owner = owner or (
        PortfolioOwner.NEI if institution == "Bradesco" else PortfolioOwner.JOLIKA
    )
    base = PortfolioPosition(
        institution=institution,
        owner=owner,
        account=f"{institution}-account",
        asset_class="Equity",
        asset_subclass="Stock",
        asset_name=f"Asset {identifier}",
        identifier=identifier,
        identifier_type="Ticker",
        quantity=Decimal("2"),
        unit_price=Decimal("50"),
        market_value=Decimal(value),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("institution", "owner"),
    (
        ("UBS", PortfolioOwner.JOLIKA),
        ("Santander", PortfolioOwner.JOLIKA),
        ("Bradesco", PortfolioOwner.NEI),
    ),
)
def test_consolidates_each_institution_in_isolation(institution, owner):
    result = PortfolioConsolidationEngine().consolidate(
        [position(institution, "AAA", owner=owner)]
    )

    assert len(result.positions) == 1
    assert result.positions[0].origins[0].institution == institution
    assert result.positions[0].owner is owner
    assert result.report.statistics.positions_by_institution == {institution: 1}


@pytest.mark.parametrize(
    "institutions",
    (
        ("UBS", "Santander"),
        ("UBS", "Bradesco"),
        ("Santander", "Bradesco"),
        ("UBS", "Santander", "Bradesco"),
    ),
)
def test_consolidates_multiple_institutions(institutions):
    portfolios = [[position(name, name.upper())] for name in institutions]

    result = PortfolioConsolidationEngine().consolidate(*portfolios)

    assert len(result.positions) == len(institutions)
    assert result.report.statistics.positions_by_institution == {
        name: 1 for name in sorted(institutions)
    }
    assert result.report.statistics.original_positions == len(institutions)


def test_groups_repeated_assets_and_preserves_every_origin_and_original():
    ubs = position("UBS", "AAA", "100")
    santander = position("Santander", " aaa ", "150", quantity=Decimal("3"))

    result = PortfolioConsolidationEngine().consolidate([ubs], [santander])

    consolidated = result.positions[0]
    assert consolidated.market_value == Decimal("250")
    assert consolidated.quantity == Decimal("5")
    assert [origin.original_position for origin in consolidated.origins] == [santander, ubs]
    assert {origin.institution for origin in consolidated.origins} == {"UBS", "Santander"}
    assert all(origin.owner is PortfolioOwner.JOLIKA for origin in consolidated.origins)
    assert {origin.original_identifier for origin in consolidated.origins} == {"AAA", " aaa "}
    assert result.report.duplicates[0].across_institutions is True
    assert result.report.duplicates[0].within_same_institution is False


def test_records_same_institution_duplicates_without_discarding_them():
    originals = [position("UBS", "AAA", "10"), position("UBS", "AAA", "20")]

    result = PortfolioConsolidationEngine().consolidate(originals)

    assert len(result.positions[0].origins) == 2
    assert result.report.duplicates[0].within_same_institution is True
    assert "within the same institution" in result.report.alerts[0]


def test_keeps_exclusive_assets_separate():
    result = PortfolioConsolidationEngine().consolidate(
        [position("UBS", "AAA"), position("Santander", "BBB")]
    )

    assert len(result.positions) == 2
    assert result.report.duplicates == ()
    assert result.report.alerts == ()


def test_never_mixes_multiple_owners_even_for_the_same_asset():
    result = PortfolioConsolidationEngine().consolidate(
        [
            position("UBS", "AAA", owner=PortfolioOwner.JOLIKA),
            position("Bradesco", "AAA", owner=PortfolioOwner.NEI),
        ]
    )

    assert len(result.positions) == 2
    assert result.report.statistics.positions_by_owner == {"JOLIKA": 1, "NEI": 1}
    assert result.report.duplicates == ()


def test_produces_all_standard_statistics():
    result = PortfolioConsolidationEngine().consolidate(
        [
            position("UBS", "AAA", "100"),
            position("Santander", "AAA", "150"),
            position(
                "Santander", "BOND", "50", asset_class="Fixed Income", asset_subclass="Bond"
            ),
        ]
    )

    statistics = result.report.statistics
    assert statistics.consolidated_value_by_currency == {"USD": Decimal("300")}
    assert statistics.positions_by_institution == {"Santander": 2, "UBS": 1}
    assert statistics.positions_by_owner == {"JOLIKA": 3}
    assert statistics.positions_by_class == {"Equity": 2, "Fixed Income": 1}
    assert statistics.positions_by_category == {"Bond": 1, "Stock": 2}
    assert statistics.unique_assets == 2
    assert statistics.original_positions == 3
    assert "3 original position(s)" in result.report.summary


def test_is_deterministic_and_does_not_modify_original_positions():
    originals = [position("UBS", "BBB"), position("Santander", "AAA")]
    snapshots = [replace(item) for item in originals]

    forward = PortfolioConsolidationEngine().consolidate(originals)
    reverse = PortfolioConsolidationEngine().consolidate(reversed(originals))

    assert forward == reverse
    assert originals == snapshots
    assert all(
        origin.original_position is originals[index]
        for index, origin in enumerate(reversed(tuple(
            item.origins[0] for item in forward.positions
        )))
    )


def test_sums_quantity_only_when_available_for_every_source_position():
    result = PortfolioConsolidationEngine().consolidate(
        [position("UBS", "AAA"), position("Santander", "AAA", quantity=None)]
    )

    assert result.positions[0].quantity is None


def test_returns_standard_empty_consolidation():
    result = PortfolioConsolidationEngine().consolidate([])

    assert result.positions == ()
    assert result.report.statistics.consolidated_value_by_currency == {}
    assert result.report.statistics.unique_assets == 0
    assert result.report.statistics.original_positions == 0
    assert result.report.duplicates == ()
    assert result.report.summary == (
        "0 original position(s) consolidated into 0 unique asset(s); "
        "0 duplicate group(s) recorded."
    )


def test_legacy_consolidation_contract_remains_compatible():
    positions = [position("UBS", "AAA", "20"), position("Santander", "BBB", "30")]

    result = consolidate_portfolio_positions(positions)

    assert result.positions_by_institution["UBS"] == (positions[0],)
    assert result.consolidated_positions == tuple(positions)
    assert result.totals_by_currency == {"USD": Decimal("50")}
