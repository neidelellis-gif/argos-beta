from __future__ import annotations

from decimal import Decimal

import pytest

from backend.market.market_connector import MarketConnector
from backend.market.models import PriceHistory, PricePoint, Quote
from backend.market.provider_base import MarketProvider
from backend.models import (
    EconomicAssetClass,
    PortfolioOwner,
    PortfolioPosition,
)
from backend.ubs_daily_intelligence import (
    UBSDailyIntelligenceService,
)


class FakeProvider(MarketProvider):
    name = "Fake"

    def __init__(self, histories=None):
        self.histories = histories or {}
        self.history_requests = []

    def get_quote(self, ticker):
        return Quote.unavailable(
            ticker,
            provider=self.name,
        )

    def get_history(self, ticker, *, days):
        self.history_requests.append(
            (ticker, days)
        )

        return self.histories.get(
            ticker,
            PriceHistory.unavailable(
                ticker,
                provider=self.name,
                error="not found",
            ),
        )


def history(ticker, prices):
    return PriceHistory(
        ticker=ticker,
        currency="USD",
        provider="Fake",
        points=tuple(
            PricePoint(
                date=f"2026-01-{index:02d}",
                close=float(price),
            )
            for index, price in enumerate(
                prices,
                start=1,
            )
        ),
        status="ok",
    )


def position(
    *,
    institution="UBS",
    owner=PortfolioOwner.JOLIKA,
    identifier="AAA",
    value="100",
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=None,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=identifier,
        identifier=identifier,
        identifier_type="TICKER",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal(value),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="portfolio.csv",
        economic_asset_class=EconomicAssetClass.EQUITIES,
    )


def service(histories=None, *, history_days=252):
    provider = FakeProvider(
        histories
    )
    connector = MarketConnector(
        providers=[provider],
        cache_ttl_seconds=300,
    )

    return (
        UBSDailyIntelligenceService(
            connector,
            history_days=history_days,
        ),
        provider,
    )


def test_returns_none_when_ubs_is_absent():
    intelligence_service, provider = service()

    result = intelligence_service.build(
        [
            position(
                institution="Santander",
                identifier="AAA",
            )
        ]
    )

    assert result is None
    assert provider.history_requests == []


def test_filters_only_jolika_ubs_positions():
    intelligence_service, provider = service(
        {
            "AAA": history(
                "AAA",
                [100, 101, 100, 102, 101],
            )
        }
    )

    result = intelligence_service.build(
        [
            position(
                institution="UBS",
                identifier="AAA",
            ),
            position(
                institution="Santander",
                identifier="BBB",
            ),
        ]
    )

    assert result is not None
    assert result.structural.institution == "UBS"
    assert result.structural.position_count == 1

    assert provider.history_requests == [
        ("AAA", 252)
    ]


def test_builds_structural_quantitative_and_operational_layers():
    intelligence_service, _ = service(
        {
            "AAA": history(
                "AAA",
                [
                    100,
                    110,
                    100,
                    112,
                    95,
                    115,
                    90,
                ],
            )
        }
    )

    result = intelligence_service.build(
        [position()]
    )

    assert result is not None

    assert result.structural.institution == "UBS"
    assert result.quantitative.institution == "UBS"
    assert result.operational.institution == "UBS"

    assert (
        result.operational.quantitative_level
        == result.quantitative.assessment.level
    )


def test_preserves_requested_history_window():
    intelligence_service, provider = service(
        {
            "AAA": history(
                "AAA",
                [100, 101, 102],
            )
        },
        history_days=90,
    )

    result = intelligence_service.build(
        [position()]
    )

    assert result is not None
    assert provider.history_requests == [
        ("AAA", 90)
    ]


def test_unavailable_history_preserves_structural_intelligence():
    intelligence_service, _ = service()

    result = intelligence_service.build(
        [position()]
    )

    assert result is not None

    assert result.structural.position_count == 1
    assert (
        result.quantitative.analyzed_position_count
        == 0
    )
    assert (
        result.quantitative.unavailable_position_count
        == 1
    )
    assert (
        result.operational.analyzed_quantitative_positions
        == 0
    )


def test_rejects_invalid_history_days():
    connector = MarketConnector(
        providers=[FakeProvider()]
    )

    with pytest.raises(
        ValueError,
        match="history_days must be a positive integer",
    ):
        UBSDailyIntelligenceService(
            connector,
            history_days=0,
        )


def test_rejects_invalid_position_input():
    intelligence_service, _ = service()

    with pytest.raises(
        TypeError,
        match="PortfolioPosition",
    ):
        intelligence_service.build(
            [object()]
        )
