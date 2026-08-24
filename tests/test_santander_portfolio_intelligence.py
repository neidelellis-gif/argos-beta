from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.santander_portfolio_intelligence import build_santander_portfolio_intelligence


def position(
    *,
    institution="Santander",
    owner=PortfolioOwner.JOLIKA,
    identifier="AAA",
    name=None,
    value="100",
    currency="USD",
    economic_class=EconomicAssetClass.EQUITIES,
    asset_class="Equity",
    source_file="santander.csv",
    account=None,
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=account,
        asset_class=asset_class,
        asset_subclass=None,
        asset_name=name if name is not None else identifier,
        identifier=identifier,
        identifier_type="ticker" if identifier else None,
        quantity=None,
        unit_price=None,
        market_value=None if value is None else Decimal(value),
        currency=currency,
        portfolio_weight=None,
        reference_date=None,
        source_file=source_file,
        economic_asset_class=economic_class,
    )


def concentration(result, currency="USD"):
    return next(item for item in result.concentration_by_currency if item.currency == currency)


def test_empty_input_returns_empty_santander_jolika_intelligence():
    result = build_santander_portfolio_intelligence([])
    assert result.institution == "Santander"
    assert result.owner is PortfolioOwner.JOLIKA
    assert result.position_count == 0
    assert result.currencies == ()
    assert result.totals_by_currency == ()
    assert result.economic_allocation_by_currency == ()
    assert result.legacy_allocation_by_currency == ()
    assert result.concentration_by_currency == ()
    assert result.duplicate_assets == ()
    assert result.warnings == ()
    assert result.source_files == ()
    assert result.coverage.total_positions == 0


def test_result_and_nested_models_are_frozen():
    result = build_santander_portfolio_intelligence([position()])
    with pytest.raises(FrozenInstanceError):
        result.position_count = 2
    with pytest.raises(FrozenInstanceError):
        result.coverage.total_positions = 2
    with pytest.raises(FrozenInstanceError):
        concentration(result).currency = "EUR"


def test_valid_santander_jolika_position_is_accepted():
    result = build_santander_portfolio_intelligence([position()])
    assert result.position_count == 1


@pytest.mark.parametrize(
    ("positions", "message"),
    [
        ([position(institution="UBS")], "Santander"),
        ([position(owner=PortfolioOwner.NEI)], "JOLIKA"),
        ([position(), position(institution="UBS")], "Santander"),
        ([position(), position(owner=PortfolioOwner.NEI)], "JOLIKA"),
    ],
)
def test_rejects_non_santander_or_non_jolika_input(positions, message):
    with pytest.raises(ValueError, match=message):
        build_santander_portfolio_intelligence(positions)


@pytest.mark.parametrize("top_n", [0, -1, 1.5, "3", True, False, None])
def test_rejects_invalid_top_n(top_n):
    with pytest.raises(ValueError, match="positive integer"):
        build_santander_portfolio_intelligence([], top_n=top_n)


def test_calls_official_diagnostic_exactly_once():
    diagnostic = SimpleNamespace(
        position_count=1,
        currencies=("USD",),
        market_value_by_currency={"USD": Decimal("100")},
        economic_allocation_by_currency={
            "USD": {EconomicAssetClass.EQUITIES: Decimal("100")}
        },
        duplicate_assets={},
        data_quality_warnings=(),
    )
    with patch(
        "backend.santander_portfolio_intelligence.diagnose_institution",
        return_value=diagnostic,
    ) as mocked:
        result = build_santander_portfolio_intelligence([position()])
    mocked.assert_called_once()
    assert result.totals_by_currency == (("USD", Decimal("100")),)


def test_totals_and_economic_allocation_preserve_official_diagnostic_values():
    result = build_santander_portfolio_intelligence(
        [
            position(value="100", economic_class=EconomicAssetClass.EQUITIES),
            position(identifier="CASH", value="40", economic_class=EconomicAssetClass.CASH),
        ]
    )
    assert result.totals_by_currency == (("USD", Decimal("140")),)
    assert result.economic_allocation_by_currency == (
        (
            "USD",
            (
                (EconomicAssetClass.EQUITIES, Decimal("100")),
                (EconomicAssetClass.CASH, Decimal("40")),
            ),
        ),
    )


def test_legacy_allocation_is_per_currency_and_never_inferred():
    result = build_santander_portfolio_intelligence(
        [
            position(value="100", asset_class="Equity"),
            position(identifier="EUR", value="50", currency="EUR", asset_class="Bond"),
            position(identifier="NONE", value="25", asset_class=None),
        ]
    )
    assert result.legacy_allocation_by_currency == (
        ("EUR", (("Bond", Decimal("50")),)),
        ("USD", (("Equity", Decimal("100")),)),
    )


def test_economic_and_legacy_classes_remain_independent():
    result = build_santander_portfolio_intelligence(
        [
            position(
                value="100",
                economic_class=EconomicAssetClass.FIXED_INCOME,
                asset_class="Legacy Equity Label",
            )
        ]
    )
    assert result.economic_allocation_by_currency[0][1][0][0] is EconomicAssetClass.FIXED_INCOME
    assert result.legacy_allocation_by_currency == (
        ("USD", (("Legacy Equity Label", Decimal("100")),)),
    )


def test_none_market_value_is_excluded_from_ranking_but_counted_in_coverage():
    result = build_santander_portfolio_intelligence(
        [position(value=None), position(identifier="BBB", value="20")]
    )
    ranked = concentration(result).top_positions
    assert [item.identifier for item in ranked] == ["BBB"]
    assert result.coverage.positions_without_market_value == 1
    assert result.coverage.positions_with_market_value == 1


def test_ranking_is_descending_by_value_with_deterministic_tie_break():
    result = build_santander_portfolio_intelligence(
        [
            position(identifier="B", value="100"),
            position(identifier="C", value="200"),
            position(identifier="A", value="100"),
        ]
    )
    assert [item.identifier for item in concentration(result).top_positions] == ["C", "A", "B"]


def test_rankings_and_totals_are_separate_by_currency():
    result = build_santander_portfolio_intelligence(
        [position(value="100"), position(identifier="EUR", value="1000", currency="EUR")]
    )
    assert result.totals_by_currency == (("EUR", Decimal("1000")), ("USD", Decimal("100")))
    assert [item.currency for item in result.concentration_by_currency] == ["EUR", "USD"]
    assert concentration(result, "EUR").top_positions[0].identifier == "EUR"
    assert concentration(result, "USD").top_positions[0].identifier == "AAA"


def test_weights_use_decimal_and_sum_to_one_for_positive_total():
    result = build_santander_portfolio_intelligence(
        [
            position(identifier="A", value="60"),
            position(identifier="B", value="30"),
            position(identifier="C", value="10"),
        ]
    )
    weights = [item.weight_within_currency for item in concentration(result).top_positions]
    assert all(isinstance(weight, Decimal) for weight in weights)
    assert sum(weights, Decimal("0")) == Decimal("1")


@pytest.mark.parametrize("values", [("0", "0"), ("-10", "5")])
def test_non_positive_currency_total_produces_none_weights_and_concentration(values):
    result = build_santander_portfolio_intelligence(
        [position(identifier="A", value=values[0]), position(identifier="B", value=values[1])]
    )
    item = concentration(result)
    assert item.total_market_value <= 0
    assert all(exposure.weight_within_currency is None for exposure in item.top_positions)
    assert item.top_1_weight is None
    assert item.top_3_weight is None
    assert item.top_5_weight is None


def test_top_1_top_3_top_5_are_factual_sums_and_use_available_positions():
    result = build_santander_portfolio_intelligence(
        [
            position(identifier="A", value="50"),
            position(identifier="B", value="30"),
            position(identifier="C", value="20"),
        ]
    )
    item = concentration(result)
    assert item.top_1_weight == Decimal("0.5")
    assert item.top_3_weight == Decimal("1")
    assert item.top_5_weight == Decimal("1")


def test_top_positions_respects_top_n_without_changing_concentration_metrics():
    result = build_santander_portfolio_intelligence(
        [
            position(identifier="A", value="50"),
            position(identifier="B", value="30"),
            position(identifier="C", value="20"),
        ],
        top_n=1,
    )
    item = concentration(result)
    assert len(item.top_positions) == 1
    assert item.top_3_weight == Decimal("1")


def test_identifier_none_is_preserved_and_asset_label_falls_back():
    unnamed = position(identifier=None, name=None, value="10")
    unnamed = replace(unnamed, asset_name=None)
    result = build_santander_portfolio_intelligence([unnamed])
    exposure = concentration(result).top_positions[0]
    assert exposure.identifier is None
    assert exposure.asset_label == "<unnamed asset>"


def test_asset_label_prefers_name_then_identifier():
    named = position(identifier="AAA", name="Full Name")
    identifier_only = replace(position(identifier="BBB"), asset_name=None)
    result = build_santander_portfolio_intelligence([named, identifier_only])
    labels = {item.identifier: item.asset_label for item in concentration(result).top_positions}
    assert labels == {"AAA": "Full Name", "BBB": "BBB"}


def test_coverage_counts_identifier_economic_and_legacy_fields():
    result = build_santander_portfolio_intelligence(
        [
            position(),
            position(identifier=None, economic_class=None, asset_class=None, value=None),
        ]
    )
    coverage = result.coverage
    assert coverage.total_positions == 2
    assert coverage.positions_with_identifier == 1
    assert coverage.positions_without_identifier == 1
    assert coverage.positions_with_economic_class == 1
    assert coverage.positions_without_economic_class == 1
    assert coverage.positions_with_legacy_asset_class == 1
    assert coverage.positions_without_legacy_asset_class == 1


def test_duplicates_and_warnings_are_preserved_from_diagnostic():
    result = build_santander_portfolio_intelligence(
        [position(identifier="AAA"), position(identifier="aaa", value="20")]
    )
    assert result.duplicate_assets == (("AAA", 2),)
    assert "1 duplicated asset(s)" in result.warnings


def test_source_files_are_unique_and_sorted():
    result = build_santander_portfolio_intelligence(
        [
            position(source_file="z.xls"),
            position(identifier="B", source_file="a.xls"),
            position(identifier="C", source_file="z.xls"),
        ]
    )
    assert result.source_files == ("a.xls", "z.xls")


def test_input_order_does_not_change_aggregate_facts():
    positions = [
        position(identifier="A", value="100", asset_class="Equity"),
        position(identifier="B", value="20", asset_class="Bond"),
    ]
    left = build_santander_portfolio_intelligence(positions)
    right = build_santander_portfolio_intelligence(reversed(positions))
    assert left.totals_by_currency == right.totals_by_currency
    assert left.economic_allocation_by_currency == right.economic_allocation_by_currency
    assert left.legacy_allocation_by_currency == right.legacy_allocation_by_currency
    assert left.coverage == right.coverage
    assert left.source_files == right.source_files


def test_original_positions_are_not_modified():
    positions = [position()]
    original = replace(positions[0])
    build_santander_portfolio_intelligence(positions)
    assert positions == [original]
    assert positions[0] is not original


def test_no_float_is_introduced_anywhere_in_monetary_output():
    result = build_santander_portfolio_intelligence([position(value="10.25")])
    assert isinstance(result.totals_by_currency[0][1], Decimal)
    item = concentration(result)
    assert isinstance(item.total_market_value, Decimal)
    assert isinstance(item.top_positions[0].market_value, Decimal)
    assert isinstance(item.top_positions[0].weight_within_currency, Decimal)
