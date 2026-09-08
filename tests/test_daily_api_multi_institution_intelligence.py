from __future__ import annotations

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
    institution,
    identifier,
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
        source_file=f"{institution.lower()}.csv",
        economic_asset_class=EconomicAssetClass.EQUITIES,
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


def facade():
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
            ubs_intelligence_service=(
                UBSDailyIntelligenceService(
                    connector,
                    history_days=252,
                )
            ),
            santander_intelligence_service=(
                SantanderDailyIntelligenceService(
                    connector,
                    history_days=252,
                )
            ),
        ),
        provider,
    )


def test_daily_api_keeps_ubs_and_santander_separate():
    api, provider = facade()

    result = api.execute(
        request_with_positions(
            [
                position("UBS", "UBS1"),
                position("Santander", "SAN1"),
            ]
        )
    )

    assert result.contract_version == "1.5"

    intelligence = result.experience[
        "portfolio_intelligence"
    ]

    assert set(intelligence) == {
        "UBS",
        "Santander",
    }

    assert (
        intelligence["UBS"]["institution"]
        == "UBS"
    )

    assert (
        intelligence["Santander"]["institution"]
        == "Santander"
    )

    assert (
        intelligence["UBS"]["position_count"]
        == 1
    )

    assert (
        intelligence["Santander"]["position_count"]
        == 1
    )

    assert set(provider.requests) == {
        ("UBS1", 252),
        ("SAN1", 252),
    }


def test_failure_in_one_institution_does_not_remove_the_other():
    class BrokenSantanderService:
        def build(self, positions):
            raise RuntimeError("Santander unavailable")

    provider = FakeProvider(
        {
            "UBS1": history(
                "UBS1",
                [100, 101, 99, 102, 100],
            )
        }
    )

    connector = MarketConnector(
        providers=[provider],
        cache_ttl_seconds=300,
    )

    api = DailyApiFacade(
        clock=lambda: datetime(
            2026,
            8,
            24,
            12,
            0,
            tzinfo=timezone.utc,
        ),
        ubs_intelligence_service=(
            UBSDailyIntelligenceService(
                connector,
                history_days=252,
            )
        ),
        santander_intelligence_service=(
            BrokenSantanderService()
        ),
    )

    result = api.execute(
        request_with_positions(
            [
                position("UBS", "UBS1"),
                position("Santander", "SAN1"),
            ]
        )
    )

    intelligence = result.experience[
        "portfolio_intelligence"
    ]

    assert set(intelligence) == {"UBS"}
    assert intelligence["UBS"]["institution"] == "UBS"

def test_daily_api_does_not_consolidate_jolika_before_authorization():
    from backend.jolika_daily_intelligence import JolikaDailyIntelligenceService

    provider = FakeProvider(
        {
            "UBS1": history("UBS1", [100, 101, 99, 102, 100]),
            "SAN1": history("SAN1", [100, 99, 101, 98, 102]),
        }
    )

    connector = MarketConnector(
        providers=[provider],
        cache_ttl_seconds=300,
    )

    api = DailyApiFacade(
        clock=lambda: datetime(
            2026,
            8,
            24,
            12,
            0,
            tzinfo=timezone.utc,
        ),
        ubs_intelligence_service=UBSDailyIntelligenceService(
            connector,
            history_days=252,
        ),
        santander_intelligence_service=SantanderDailyIntelligenceService(
            connector,
            history_days=252,
        ),
        jolika_intelligence_service=JolikaDailyIntelligenceService(),
    )

    result = api.execute(
        request_with_positions(
            [
                position("UBS", "UBS1"),
                position("Santander", "SAN1"),
            ]
        ),
        consolidation_authorized=False,
    )

    intelligence = result.experience["portfolio_intelligence"]

    assert set(intelligence) == {"UBS", "Santander"}
    assert "JOLIKA" not in intelligence


def test_daily_api_context_respects_consolidation_authorization():
    from backend.daily_api import daily_consolidation_authorization
    from backend.jolika_daily_intelligence import (
        JolikaDailyIntelligenceService,
    )

    provider = FakeProvider(
        {
            "UBS1": history("UBS1", [100, 101, 99, 102, 100]),
            "SAN1": history("SAN1", [100, 99, 101, 98, 102]),
        }
    )

    connector = MarketConnector(
        providers=[provider],
        cache_ttl_seconds=300,
    )

    api = DailyApiFacade(
        clock=lambda: datetime(
            2026,
            8,
            24,
            12,
            0,
            tzinfo=timezone.utc,
        ),
        ubs_intelligence_service=UBSDailyIntelligenceService(
            connector,
            history_days=252,
        ),
        santander_intelligence_service=SantanderDailyIntelligenceService(
            connector,
            history_days=252,
        ),
        jolika_intelligence_service=JolikaDailyIntelligenceService(),
    )

    request = request_with_positions(
        [
            position("UBS", "UBS1"),
            position("Santander", "SAN1"),
        ]
    )

    with daily_consolidation_authorization(False):
        blocked = api.execute(request)

    assert set(
        blocked.experience["portfolio_intelligence"]
    ) == {"UBS", "Santander"}

    with daily_consolidation_authorization(True):
        authorized = api.execute(request)

    assert set(
        authorized.experience["portfolio_intelligence"]
    ) == {"UBS", "Santander", "JOLIKA"}
