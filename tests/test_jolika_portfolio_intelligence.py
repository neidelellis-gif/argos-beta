from datetime import date
from decimal import Decimal

import pytest

from backend.jolika_portfolio_intelligence import (
    build_jolika_portfolio_intelligence,
)
from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


def position(
    *,
    institution="UBS",
    owner=PortfolioOwner.JOLIKA,
    account="A1",
    asset_class="Ação",
    asset_subclass=None,
    asset_name="Asset",
    identifier="AAA",
    identifier_type="TICKER",
    quantity=None,
    unit_price=None,
    market_value="100",
    currency="USD",
    portfolio_weight=None,
    reference_date=date(2026, 8, 19),
    source_file="source.xlsx",
    economic_asset_class=EconomicAssetClass.EQUITIES,
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=account,
        asset_class=asset_class,
        asset_subclass=asset_subclass,
        asset_name=asset_name,
        identifier=identifier,
        identifier_type=identifier_type,
        quantity=Decimal(str(quantity)) if quantity is not None else None,
        unit_price=Decimal(str(unit_price)) if unit_price is not None else None,
        market_value=(
            Decimal(str(market_value))
            if market_value is not None
            else None
        ),
        currency=currency,
        portfolio_weight=(
            Decimal(str(portfolio_weight))
            if portfolio_weight is not None
            else None
        ),
        reference_date=reference_date,
        source_file=source_file,
        economic_asset_class=economic_asset_class,
    )


def test_empty_portfolio_builds_empty_intelligence():
    result = build_jolika_portfolio_intelligence([])

    assert result.owner is PortfolioOwner.JOLIKA
    assert result.original_position_count == 0
    assert result.consolidated_asset_count == 0
    assert result.institutions == ()
    assert result.currencies == ()
    assert result.totals_by_currency == ()
    assert result.economic_allocation_by_currency == ()
    assert result.concentration_by_currency == ()
    assert result.duplicate_exposures == ()
    assert result.consolidation_alerts == ()
    assert result.source_files == ()


def test_rejects_non_jolika_position():
    with pytest.raises(ValueError, match="all positions must belong to JOLIKA"):
        build_jolika_portfolio_intelligence(
            [position(owner=PortfolioOwner.NEI)]
        )


@pytest.mark.parametrize("top_n", [0, -1, True, 1.5, "10"])
def test_rejects_invalid_top_n(top_n):
    with pytest.raises(ValueError, match="top_n must be a positive integer"):
        build_jolika_portfolio_intelligence([], top_n=top_n)


def test_totals_and_economic_allocation_are_currency_safe():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                market_value="100",
                currency="USD",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier="BBB",
                market_value="50",
                currency="USD",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
            position(
                identifier="CCC",
                market_value="200",
                currency="BRL",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
        ]
    )

    assert result.totals_by_currency == (
        ("BRL", Decimal("200")),
        ("USD", Decimal("150")),
    )

    allocation = dict(result.economic_allocation_by_currency)

    assert dict(allocation["BRL"]) == {
        EconomicAssetClass.FIXED_INCOME: Decimal("200")
    }
    assert dict(allocation["USD"]) == {
        EconomicAssetClass.EQUITIES: Decimal("100"),
        EconomicAssetClass.FIXED_INCOME: Decimal("50"),
    }


def test_duplicate_asset_across_institutions_is_consolidated():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                institution="UBS",
                identifier="AAA",
                asset_name="Alpha",
                market_value="100",
                source_file="ubs.xlsx",
            ),
            position(
                institution="Santander",
                identifier="AAA",
                asset_name="Alpha",
                market_value="50",
                source_file="santander.xlsx",
            ),
        ]
    )

    assert result.original_position_count == 2
    assert result.consolidated_asset_count == 1
    assert result.institutions == ("Santander", "UBS")
    assert result.totals_by_currency == (("USD", Decimal("150")),)
    assert len(result.duplicate_exposures) == 1

    duplicate = result.duplicate_exposures[0]

    assert duplicate.asset_key == "aaa"
    assert duplicate.institutions == ("Santander", "UBS")
    assert duplicate.across_institutions is True
    assert duplicate.within_same_institution is False
    assert duplicate.source_position_count == 2
    assert (
        "Duplicate positions found across institutions"
        in result.consolidation_alerts
    )


def test_concentration_uses_consolidated_assets():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                institution="UBS",
                identifier="AAA",
                asset_name="Alpha",
                market_value="60",
                source_file="ubs.xlsx",
            ),
            position(
                institution="Santander",
                identifier="AAA",
                asset_name="Alpha",
                market_value="40",
                source_file="santander.xlsx",
            ),
            position(
                institution="UBS",
                identifier="BBB",
                asset_name="Beta",
                market_value="50",
                source_file="ubs.xlsx",
            ),
        ],
        top_n=10,
    )

    concentration = result.concentration_by_currency[0]

    assert concentration.currency == "USD"
    assert concentration.total_market_value == Decimal("150")
    assert concentration.asset_count == 2

    top = concentration.top_positions[0]

    assert top.identifier == "AAA"
    assert top.market_value == Decimal("100")
    assert top.weight_within_currency == Decimal("100") / Decimal("150")
    assert top.institution_count == 2
    assert top.institutions == ("Santander", "UBS")

    assert concentration.top_1_weight == Decimal("100") / Decimal("150")
    assert concentration.top_3_weight == Decimal("1")
    assert concentration.top_5_weight == Decimal("1")


def test_coverage_counts_consolidated_assets():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier=None,
                asset_name="Unknown",
                economic_asset_class=None,
                source_file="unknown.xlsx",
            ),
        ]
    )

    coverage = result.coverage

    assert coverage.original_position_count == 2
    assert coverage.consolidated_asset_count == 2
    assert coverage.assets_with_economic_class == 1
    assert coverage.assets_without_economic_class == 1
    assert coverage.assets_with_identifier == 1
    assert coverage.assets_without_identifier == 1


def test_source_files_are_unique_and_sorted():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                source_file="z.xlsx",
            ),
            position(
                identifier="BBB",
                source_file="a.xlsx",
            ),
            position(
                identifier="CCC",
                source_file="z.xlsx",
            ),
        ]
    )

    assert result.source_files == ("a.xlsx", "z.xlsx")


def test_result_is_deterministic_for_input_order():
    positions = [
        position(
            institution="UBS",
            identifier="AAA",
            asset_name="Alpha",
            market_value="100",
            source_file="ubs.xlsx",
        ),
        position(
            institution="Santander",
            identifier="AAA",
            asset_name="Alpha",
            market_value="50",
            source_file="santander.xlsx",
        ),
        position(
            institution="UBS",
            identifier="BBB",
            asset_name="Beta",
            market_value="75",
            source_file="ubs.xlsx",
        ),
    ]

    forward = build_jolika_portfolio_intelligence(positions)
    reverse = build_jolika_portfolio_intelligence(reversed(positions))

    assert forward == reverse


def test_priority_is_high_for_severe_concentration():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                asset_name="Alpha",
                market_value="70",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier="BBB",
                asset_name="Beta",
                market_value="30",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
        ]
    )

    assert result.priority.level == "Alta"
    assert "concentration" in result.priority.reasons


def test_priority_is_medium_for_moderate_concentration():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                asset_name="Alpha",
                market_value="30",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier="BBB",
                asset_name="Beta",
                market_value="25",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
            position(
                identifier="CCC",
                asset_name="Gamma",
                market_value="25",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
            position(
                identifier="DDD",
                asset_name="Delta",
                market_value="20",
                economic_asset_class=EconomicAssetClass.CASH,
            ),
        ]
    )

    assert result.priority.level == "Média"
    assert "concentration" in result.priority.reasons


def test_priority_is_low_for_well_distributed_fully_classified_portfolio():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                asset_name="Alpha",
                market_value="20",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier="BBB",
                asset_name="Beta",
                market_value="20",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
            position(
                identifier="CCC",
                asset_name="Gamma",
                market_value="20",
                economic_asset_class=EconomicAssetClass.CASH,
            ),
            position(
                identifier="DDD",
                asset_name="Delta",
                market_value="20",
                economic_asset_class=EconomicAssetClass.FUNDS_STRATEGIES,
            ),
            position(
                identifier="EEE",
                asset_name="Epsilon",
                market_value="20",
                economic_asset_class=EconomicAssetClass.GOLD_AND_COMMODITIES,
            ),
        ]
    )

    assert result.priority.level == "Baixa"
    assert result.priority.reasons == ()


def test_materiality_is_high_for_dominant_position():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                asset_name="Alpha",
                market_value="70",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier="BBB",
                asset_name="Beta",
                market_value="30",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
        ]
    )

    assert result.materiality.level == "Alta"
    assert result.materiality.max_position_weight == Decimal("0.7")
    assert result.materiality.driver == "concentration"


def test_materiality_is_medium_for_relevant_but_not_dominant_position():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                asset_name="Alpha",
                market_value="30",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier="BBB",
                asset_name="Beta",
                market_value="25",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
            position(
                identifier="CCC",
                asset_name="Gamma",
                market_value="25",
                economic_asset_class=EconomicAssetClass.CASH,
            ),
            position(
                identifier="DDD",
                asset_name="Delta",
                market_value="20",
                economic_asset_class=EconomicAssetClass.FUNDS_STRATEGIES,
            ),
        ]
    )

    assert result.materiality.level == "Média"
    assert result.materiality.max_position_weight == Decimal("0.3")
    assert result.materiality.driver == "concentration"


def test_materiality_is_low_for_well_distributed_positions():
    result = build_jolika_portfolio_intelligence(
        [
            position(
                identifier="AAA",
                asset_name="Alpha",
                market_value="20",
                economic_asset_class=EconomicAssetClass.EQUITIES,
            ),
            position(
                identifier="BBB",
                asset_name="Beta",
                market_value="20",
                economic_asset_class=EconomicAssetClass.FIXED_INCOME,
            ),
            position(
                identifier="CCC",
                asset_name="Gamma",
                market_value="20",
                economic_asset_class=EconomicAssetClass.CASH,
            ),
            position(
                identifier="DDD",
                asset_name="Delta",
                market_value="20",
                economic_asset_class=EconomicAssetClass.FUNDS_STRATEGIES,
            ),
            position(
                identifier="EEE",
                asset_name="Epsilon",
                market_value="20",
                economic_asset_class=EconomicAssetClass.GOLD_AND_COMMODITIES,
            ),
        ]
    )

    assert result.materiality.level == "Baixa"
    assert result.materiality.max_position_weight == Decimal("0.2")
    assert result.materiality.driver is None
