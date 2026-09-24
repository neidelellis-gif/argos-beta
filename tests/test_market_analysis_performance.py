from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from time import sleep

from backend.market.market_connector import MarketConnector
from backend.market.models import PriceHistory, PricePoint, Quote
from backend.market.provider_base import MarketProvider
from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.ubs_quantitative_intelligence import build_ubs_quantitative_intelligence


class ConcurrentHistoryProvider(MarketProvider):
    name = "ConcurrentFake"

    def __init__(self) -> None:
        self._lock = Lock()
        self.active = 0
        self.max_active = 0

    def get_quote(self, ticker: str) -> Quote:
        return Quote.unavailable(ticker, provider=self.name)

    def get_history(self, ticker: str, *, days: int) -> PriceHistory:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            sleep(0.03)
            return PriceHistory(
                ticker=ticker,
                currency="USD",
                provider=self.name,
                points=(
                    PricePoint(date="2026-09-20", close=100.0),
                    PricePoint(date="2026-09-21", close=101.0),
                    PricePoint(date="2026-09-22", close=102.0),
                ),
                status="ok",
            )
        finally:
            with self._lock:
                self.active -= 1


def position(identifier: str) -> PortfolioPosition:
    return PortfolioPosition(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=identifier,
        identifier=identifier,
        identifier_type="TICKER",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=datetime(2026, 9, 24, tzinfo=timezone.utc).date(),
        source_file="ubs.csv",
        economic_asset_class=EconomicAssetClass.EQUITIES,
    )


def test_ubs_history_requests_are_parallel_and_results_remain_deterministic() -> None:
    provider = ConcurrentHistoryProvider()
    connector = MarketConnector(providers=[provider], history_cache_ttl_seconds=86400)
    positions = tuple(position(identifier) for identifier in ("DDD", "AAA", "CCC", "BBB"))

    result = build_ubs_quantitative_intelligence(
        positions,
        market_connector=connector,
        lookback_days=252,
    )

    assert provider.max_active >= 2
    assert tuple(item.identifier for item in result.positions) == (
        "AAA",
        "BBB",
        "CCC",
        "DDD",
    )
    assert result.analyzed_position_count == 4
