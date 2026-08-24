from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from backend.daily_api import DailyApiFacade
from backend.daily_contract import DailyApiRequest
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
        self.requests = []

    def get_quote(self, ticker):
        return Quote.unavailable(
            ticker,
            provider=self.name,
        )

    def get_history(self, ticker, *, days):
        self.requests.append((ticker, days))

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
    identifier="AAA",
    value="100",
):
    return PortfolioPosition(
        institution=institution,
        owner=PortfolioOwner.JOLIKA,
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
        source_file="ubs.csv",
        economic_asset_class=EconomicAssetClass.EQUITIES,
    )


def facade(histories=None):
    provider = FakeProvider(histories)
    connector = MarketConnector(
        providers=[provider],
        cache_ttl_seconds=300,
    )

    service = UBSDailyIntelligenceService(
        connector,
        history_days=252,
    )

    return (
        DailyApiFacade(
            clock=lambda: datetime(
                2026,
                8,
                24,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            ubs_intelligence_service=service,
        ),
        provider,
    )


def request_with_positions(positions):
    return DailyApiRequest(
        positions=tuple(positions),
        fact_candidates=(),
        reference_date=datetime(
            2026,
            8,
            24,
            tzinfo=timezone.utc,
        ).date(),
    )


def test_daily_api_without_service_preserves_existing_contract():
    result = DailyApiFacade(
        clock=lambda: datetime(
            2026,
            8,
            24,
            12,
            0,
            tzinfo=timezone.utc,
        )
    ).execute(
        request_with_positions([])
    )

    assert result.contract_version == "1.5"
    assert result.experience is not None
    assert "status" in result.experience
    assert "portfolio_intelligence" not in result.experience


def test_daily_api_does_not_emit_ubs_component_when_ubs_is_absent():
    api, provider = facade()

    result = api.execute(
        request_with_positions(
            [
                position(
                    institution="Santander",
                    identifier="SAN",
                )
            ]
        )
    )

    assert result.contract_version == "1.5"
    assert "portfolio_intelligence" not in result.experience
    assert provider.requests == []


def test_daily_api_exposes_ubs_portfolio_intelligence():
    api, provider = facade(
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

    result = api.execute(
        request_with_positions(
            [position()]
        )
    )

    assert result.contract_version == "1.5"

    intelligence = result.experience[
        "portfolio_intelligence"
    ]["UBS"]

    assert intelligence["institution"] == "UBS"
    assert intelligence["owner"] == "JOLIKA"
    assert intelligence["position_count"] == 1

    assert intelligence["overall_level"] in {
        "Baixa",
        "Média",
        "Alta",
    }

    assert intelligence["structural_level"] in {
        "Baixa",
        "Média",
        "Alta",
    }

    assert intelligence["quantitative_level"] in {
        "Baixa",
        "Média",
        "Alta",
    }

    assert intelligence["executive_reading"]

    assert intelligence[
        "quantitative_coverage"
    ]["lookback_days"] == 252

    assert provider.requests == [
        ("AAA", 252)
    ]


def test_daily_api_keeps_quantitative_unavailability_visible():
    api, _ = facade()

    result = api.execute(
        request_with_positions(
            [position()]
        )
    )

    intelligence = result.experience[
        "portfolio_intelligence"
    ]["UBS"]

    coverage = intelligence[
        "quantitative_coverage"
    ]

    assert coverage["analyzed_positions"] == 0
    assert coverage["unavailable_positions"] == 1


def test_ubs_intelligence_does_not_become_market_fact():
    api, _ = facade(
        {
            "AAA": history(
                "AAA",
                [
                    100,
                    110,
                    90,
                    115,
                    85,
                    120,
                ],
            )
        }
    )

    result = api.execute(
        request_with_positions(
            [position()]
        )
    )

    assert (
        "portfolio_intelligence"
        in result.experience
    )

    assert all(
        fact.category != "UBS_PORTFOLIO_INTELLIGENCE"
        for fact in result.facts
    )


def test_ubs_intelligence_does_not_create_artificial_analysis():
    api, _ = facade(
        {
            "AAA": history(
                "AAA",
                [
                    100,
                    110,
                    90,
                    115,
                    85,
                    120,
                ],
            )
        }
    )

    result = api.execute(
        request_with_positions(
            [position()]
        )
    )

    assert (
        "portfolio_intelligence"
        in result.experience
    )

    assert all(
        "UBS" not in analysis.title
        or analysis.fact_id
        for analysis in result.analyses
    )


def test_market_intelligence_failure_never_breaks_daily_experience():
    class BrokenService:
        def build(self, positions):
            raise RuntimeError("market failure")

    api = DailyApiFacade(
        clock=lambda: datetime(
            2026,
            8,
            24,
            12,
            0,
            tzinfo=timezone.utc,
        ),
        ubs_intelligence_service=BrokenService(),
    )

    result = api.execute(
        request_with_positions(
            [position()]
        )
    )

    assert result.status.value == "SUCCESS"
    assert "portfolio_intelligence" not in result.experience
