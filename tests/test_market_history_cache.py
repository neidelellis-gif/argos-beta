from backend.market.market_connector import MarketConnector
from backend.market.models import PriceHistory, PricePoint
from backend.market.persistent_history_cache import PersistentHistoryCache


def ok_history(ticker="SPY", provider="Fake", close=100.0):
    return PriceHistory(
        ticker=ticker,
        currency="USD",
        provider=provider,
        points=(PricePoint(date="2026-08-24", close=close),),
        status="ok",
        error=None,
    )


class FakeProvider:
    name = "Fake"
    def __init__(self, result=None):
        self.result = result
        self.calls = []
    def get_history(self, ticker, *, days):
        self.calls.append((ticker, days))
        if self.result is None:
            return PriceHistory.unavailable(ticker, provider=self.name, error="temporary failure")
        return self.result
    def get_quote(self, ticker):
        raise NotImplementedError


def test_memory_history_cache_reuses_request():
    provider = FakeProvider(ok_history())
    connector = MarketConnector(providers=[provider], history_cache_ttl_seconds=86400)
    assert connector.get_history("SPY", days=252).status == "ok"
    assert connector.get_history("SPY", days=252).status == "ok"
    assert provider.calls == [("SPY", 252)]


def test_history_cache_key_includes_days():
    provider = FakeProvider(ok_history())
    connector = MarketConnector(providers=[provider], history_cache_ttl_seconds=86400)
    connector.get_history("SPY", days=252)
    connector.get_history("SPY", days=30)
    assert provider.calls == [("SPY", 252), ("SPY", 30)]


def test_persistent_cache_survives_new_connector(tmp_path):
    first = MarketConnector(
        providers=[FakeProvider(ok_history(close=101.0))],
        history_cache_ttl_seconds=86400,
        persistent_history_cache_dir=tmp_path,
    )
    assert first.get_history("SPY", days=252).points[0].close == 101.0
    second_provider = FakeProvider()
    second = MarketConnector(
        providers=[second_provider],
        history_cache_ttl_seconds=86400,
        persistent_history_cache_dir=tmp_path,
    )
    assert second.get_history("SPY", days=252).points[0].close == 101.0
    assert second_provider.calls == []


def test_unavailable_is_not_persisted(tmp_path):
    connector = MarketConnector(
        providers=[FakeProvider()],
        history_cache_ttl_seconds=86400,
        persistent_history_cache_dir=tmp_path,
    )
    assert connector.get_history("SPY", days=252).status == "unavailable"
    assert list(tmp_path.glob("*.json")) == []


def test_corrupt_cache_is_ignored(tmp_path):
    cache = PersistentHistoryCache(tmp_path, ttl_seconds=86400)
    path = cache._path_for("SPY:252")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad-json", encoding="utf-8")
    assert cache.get("SPY:252") is None


def test_clear_cache_preserves_persistent_by_default(tmp_path):
    connector = MarketConnector(
        providers=[FakeProvider(ok_history())],
        history_cache_ttl_seconds=86400,
        persistent_history_cache_dir=tmp_path,
    )
    connector.get_history("SPY", days=252)
    connector.clear_cache()
    assert len(list(tmp_path.glob("*.json"))) == 1
    connector.clear_cache(persistent=True)
    assert list(tmp_path.glob("*.json")) == []
