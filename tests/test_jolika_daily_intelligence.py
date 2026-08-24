from __future__ import annotations

from decimal import Decimal

from backend.jolika_daily_intelligence import (
    JolikaDailyIntelligenceService,
)
from backend.market.market_connector import MarketConnector
from backend.market.models import PriceHistory, PricePoint, Quote
from backend.market.provider_base import MarketProvider
from backend.models import (
    EconomicAssetClass,
    PortfolioOwner,
    PortfolioPosition,
)
from backend.santander_daily_intelligence import (
    SantanderDailyIntelligenceService,
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
        self.history_requests.append((ticker, days))

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
            for index, price in enumerate(prices, start=1)
        ),
        status="ok",
    )


def position(institution, identifier, value="100"):
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
        source_file=f"{institution.lower()}.csv",
        economic_asset_class=EconomicAssetClass.EQUITIES,
    )


def institutional_results():
    provider = FakeProvider(
        {
            "UBS1": history(
                "UBS1",
                [100, 101, 99, 102, 100],
            ),
            "SAN1": history(
                "SAN1",
                [100, 99, 101, 98, 102],
            ),
        }
    )

    connector = MarketConnector(
        providers=[provider],
        cache_ttl_seconds=300,
    )

    ubs_position = position(
        "UBS",
        "UBS1",
        "200",
    )
    santander_position = position(
        "Santander",
        "SAN1",
        "100",
    )

    ubs = UBSDailyIntelligenceService(
        connector,
        history_days=252,
    ).build(
        [ubs_position]
    )

    santander = SantanderDailyIntelligenceService(
        connector,
        history_days=252,
    ).build(
        [santander_position]
    )

    assert ubs is not None
    assert santander is not None

    return (
        provider,
        ubs,
        santander,
        ubs_position,
        santander_position,
    )


def test_returns_none_without_institutional_results():
    service = JolikaDailyIntelligenceService()

    assert service.build(()) is None


def test_builds_consolidated_jolika_from_both_banks():
    _, ubs, santander, ubs_position, santander_position = (
        institutional_results()
    )

    result = JolikaDailyIntelligenceService().build(
        (
            ubs_position,
            santander_position,
        ),
        ubs=ubs,
        santander=santander,
    )

    assert result is not None
    assert result.structural.owner is PortfolioOwner.JOLIKA
    assert result.structural.consolidated_asset_count == 2
    assert len(result.operational.institution_assessments) == 2


def test_preserves_institutional_separation():
    _, ubs, santander, ubs_position, santander_position = (
        institutional_results()
    )

    result = JolikaDailyIntelligenceService().build(
        (
            ubs_position,
            santander_position,
        ),
        ubs=ubs,
        santander=santander,
    )

    assert result is not None
    assert set(result.structural.institutions) == {
        "UBS",
        "Santander",
    }


def test_consolidation_does_not_request_market_history_again():
    provider, ubs, santander, ubs_position, santander_position = (
        institutional_results()
    )

    before = list(provider.history_requests)

    result = JolikaDailyIntelligenceService().build(
        (
            ubs_position,
            santander_position,
        ),
        ubs=ubs,
        santander=santander,
    )

    assert result is not None
    assert provider.history_requests == before


def test_can_consolidate_only_ubs_when_santander_is_unavailable():
    _, ubs, _, ubs_position, _ = institutional_results()

    result = JolikaDailyIntelligenceService().build(
        (ubs_position,),
        ubs=ubs,
    )

    assert result is not None
    assert result.structural.consolidated_asset_count == 1
    assert result.structural.institutions == ("UBS",)


def test_can_consolidate_only_santander_when_ubs_is_unavailable():
    _, _, santander, _, santander_position = institutional_results()

    result = JolikaDailyIntelligenceService().build(
        (santander_position,),
        santander=santander,
    )

    assert result is not None
    assert result.structural.consolidated_asset_count == 1
    assert result.structural.institutions == ("Santander",)


def test_public_payload_identifies_consolidated_jolika():
    _, ubs, santander, ubs_position, santander_position = (
        institutional_results()
    )

    result = JolikaDailyIntelligenceService().build(
        (
            ubs_position,
            santander_position,
        ),
        ubs=ubs,
        santander=santander,
    )

    assert result is not None

    payload = result.to_dict()

    assert payload["institution"] == "JOLIKA"
    assert payload["owner"] == PortfolioOwner.JOLIKA.value
    assert payload["position_count"] == 2
    assert set(payload["institutions"]) == {
        "UBS",
        "Santander",
    }
