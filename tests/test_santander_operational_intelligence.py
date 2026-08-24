from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from backend.market.models import PriceHistory, PricePoint
from backend.models import (
    EconomicAssetClass,
    PortfolioOwner,
    PortfolioPosition,
)
from backend.santander_operational_intelligence import (
    build_santander_operational_intelligence,
)
from backend.santander_portfolio_intelligence import (
    build_santander_portfolio_intelligence,
)
from backend.santander_quantitative_intelligence import (
    build_santander_quantitative_intelligence,
)


def position(
    *,
    identifier,
    value,
    economic_class=EconomicAssetClass.EQUITIES,
    identifier_type="ticker",
):
    return PortfolioPosition(
        institution="Santander",
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=identifier,
        identifier=identifier,
        identifier_type=identifier_type,
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal(value),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="santander.csv",
        economic_asset_class=economic_class,
    )


class FakeMarketConnector:
    def __init__(self, histories=None):
        self.histories = histories or {}

    def get_history(self, ticker, *, days):
        return self.histories.get(
            ticker,
            PriceHistory.unavailable(
                ticker,
                provider="Fake",
                error="not found",
            ),
        )


def history_from_returns(ticker, returns):
    prices = [100.0]

    for value in returns:
        prices.append(
            prices[-1] * (1.0 + value)
        )

    return PriceHistory(
        ticker=ticker,
        currency="USD",
        provider="Fake",
        points=tuple(
            PricePoint(
                date=f"2026-01-{index:02d}",
                close=price,
            )
            for index, price in enumerate(
                prices,
                start=1,
            )
        ),
        status="ok",
    )


def build_pair(
    positions,
    histories,
):
    structural = build_santander_portfolio_intelligence(
        positions
    )

    quantitative = build_santander_quantitative_intelligence(
        positions,
        market_connector=FakeMarketConnector(
            histories
        ),
    )

    return structural, quantitative


def test_combines_low_structural_and_low_quantitative_attention():
    positions = [
        position(identifier="A", value="25"),
        position(identifier="B", value="25"),
        position(identifier="C", value="25"),
        position(identifier="D", value="25"),
    ]

    low_returns = [
        0.001,
        -0.001,
        0.002,
        -0.001,
        0.001,
    ]

    structural, quantitative = build_pair(
        positions,
        {
            item.identifier: history_from_returns(
                item.identifier,
                low_returns,
            )
            for item in positions
        },
    )

    result = build_santander_operational_intelligence(
        structural,
        quantitative,
    )

    assert result.structural_level == "Média"
    assert result.quantitative_level == "Baixa"
    assert result.overall_level == "Média"


def test_high_quantitative_attention_drives_overall_attention():
    positions = [
        position(identifier="A", value="25"),
        position(identifier="B", value="25"),
        position(identifier="C", value="25"),
        position(identifier="D", value="25"),
    ]

    low_returns = [
        0.001,
        -0.001,
        0.002,
        -0.001,
        0.001,
    ]

    high_returns = [
        0.10,
        -0.09,
        0.11,
        -0.08,
        0.12,
        -0.10,
    ]

    histories = {
        "A": history_from_returns(
            "A",
            high_returns,
        ),
        "B": history_from_returns(
            "B",
            low_returns,
        ),
        "C": history_from_returns(
            "C",
            low_returns,
        ),
        "D": history_from_returns(
            "D",
            low_returns,
        ),
    }

    structural, quantitative = build_pair(
        positions,
        histories,
    )

    result = build_santander_operational_intelligence(
        structural,
        quantitative,
    )

    assert result.quantitative_level == "Alta"
    assert result.overall_level == "Alta"

    quantitative_items = [
        item
        for item in result.attention_items
        if item.source == "QUANTITATIVE"
    ]

    assert quantitative_items
    assert all(
        item.identifier == "A"
        for item in quantitative_items
    )


def test_structural_concentration_can_drive_high_attention():
    positions = [
        position(identifier="A", value="80"),
        position(identifier="B", value="10"),
        position(identifier="C", value="10"),
    ]

    low_returns = [
        0.001,
        -0.001,
        0.002,
        -0.001,
        0.001,
    ]

    structural, quantitative = build_pair(
        positions,
        {
            item.identifier: history_from_returns(
                item.identifier,
                low_returns,
            )
            for item in positions
        },
    )

    result = build_santander_operational_intelligence(
        structural,
        quantitative,
    )

    assert result.structural_level == "Alta"
    assert result.quantitative_level == "Baixa"
    assert result.overall_level == "Alta"

    assert any(
        item.source == "STRUCTURAL"
        and item.reason == "concentration"
        and item.level == "Alta"
        for item in result.attention_items
    )


def test_combined_high_structural_and_quantitative_reading():
    positions = [
        position(identifier="A", value="80"),
        position(identifier="B", value="20"),
    ]

    histories = {
        "A": history_from_returns(
            "A",
            [
                0.10,
                -0.09,
                0.11,
                -0.08,
                0.12,
                -0.10,
            ],
        ),
        "B": history_from_returns(
            "B",
            [
                0.001,
                -0.001,
                0.002,
                -0.001,
                0.001,
            ],
        ),
    }

    structural, quantitative = build_pair(
        positions,
        histories,
    )

    result = build_santander_operational_intelligence(
        structural,
        quantitative,
    )

    assert result.structural_level == "Alta"
    assert result.quantitative_level == "Alta"
    assert result.overall_level == "Alta"

    assert (
        "tanto na estrutura quanto no comportamento histórico"
        in result.executive_reading
    )


def test_unavailable_history_does_not_create_false_quantitative_risk():
    positions = [
        position(
            identifier="US1234567890",
            identifier_type="ISIN",
            value="100",
        )
    ]

    structural, quantitative = build_pair(
        positions,
        {},
    )

    result = build_santander_operational_intelligence(
        structural,
        quantitative,
    )

    assert result.analyzed_quantitative_positions == 0
    assert result.unavailable_quantitative_positions == 1
    assert result.quantitative_level == "Baixa"

    assert not any(
        item.source == "QUANTITATIVE"
        for item in result.attention_items
    )


def test_quantitative_attention_preserves_asset_traceability():
    positions = [
        position(identifier="AAA", value="50"),
        position(identifier="BBB", value="50"),
    ]

    structural, quantitative = build_pair(
        positions,
        {
            "AAA": history_from_returns(
                "AAA",
                [
                    0.10,
                    -0.09,
                    0.11,
                    -0.08,
                    0.12,
                    -0.10,
                ],
            ),
            "BBB": history_from_returns(
                "BBB",
                [
                    0.001,
                    -0.001,
                    0.002,
                    -0.001,
                    0.001,
                ],
            ),
        },
    )

    result = build_santander_operational_intelligence(
        structural,
        quantitative,
    )

    items = [
        item
        for item in result.attention_items
        if item.source == "QUANTITATIVE"
    ]

    assert items
    assert all(
        item.identifier == "AAA"
        for item in items
    )
    assert all(
        item.asset_label == "AAA"
        for item in items
    )


def test_rejects_mismatched_institution_contract():
    positions = [
        position(identifier="AAA", value="100")
    ]

    structural, quantitative = build_pair(
        positions,
        {
            "AAA": history_from_returns(
                "AAA",
                [0.001, -0.001],
            )
        },
    )

    invalid = replace(
        quantitative,
        institution="UBS",
    )

    try:
        build_santander_operational_intelligence(
            structural,
            invalid,
        )
    except ValueError as exc:
        assert "Santander" in str(exc)
    else:
        raise AssertionError(
            "expected ValueError"
        )
