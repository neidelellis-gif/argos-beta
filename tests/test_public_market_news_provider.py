from datetime import date
from decimal import Decimal
from io import BytesIO

from backend.models import PortfolioOwner, PortfolioPosition
from backend.public_market_news_provider import PublicMarketNewsProvider


class Response:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def position(identifier: str, name: str, value: str) -> PortfolioPosition:
    return PortfolioPosition(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=name,
        identifier=identifier,
        identifier_type="TICKER",
        quantity=Decimal("1"),
        unit_price=Decimal(value),
        market_value=Decimal(value),
        currency="USD",
        portfolio_weight=None,
        reference_date=date(2026, 9, 24),
        source_file="ubs.csv",
    )


def rss(title: str, description: str, guid: str = "1") -> bytes:
    return f"""<?xml version="1.0"?>
    <rss><channel><item>
      <title>{title}</title>
      <description>{description}</description>
      <guid>{guid}</guid>
      <pubDate>Thu, 24 Sep 2026 15:00:00 GMT</pubDate>
    </item></channel></rss>""".encode()


def test_public_provider_requires_no_credentials_and_matches_portfolio_asset():
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        if "federalreserve" in request.full_url:
            return Response(rss("Federal Reserve statement", "Policy update", "fed"))
        if "sec.gov" in request.full_url:
            return Response(rss("SEC market structure update", "Regulatory update", "sec"))
        return Response(rss("NVIDIA expands AI infrastructure", "NVDA capacity update", "nvda"))

    provider = PublicMarketNewsProvider(opener=opener, timeout_seconds=0.1)
    result = provider.fetch_facts(
        None,
        (position("NVDA", "NVIDIA", "200"), position("AAPL", "Apple", "100")),
    )

    assert result.status == "available"
    nvda = next(item for item in result.items if "NVIDIA" in item.title)
    assert nvda.related_assets == ("NVDA",)
    assert any("news.google.com/rss/search" in url for url in calls)


def test_fed_fact_is_related_to_usd_without_portfolio_symbol_match():
    def opener(request, timeout):
        if "federalreserve" in request.full_url:
            return Response(rss("Federal Reserve statement", "Policy update", "fed"))
        return Response(b"<rss><channel></channel></rss>")

    result = PublicMarketNewsProvider(opener=opener).fetch_facts(
        None, (position("AAPL", "Apple", "100"),)
    )

    fed = next(item for item in result.items if item.source == "Federal Reserve")
    assert fed.related_assets == ("USD",)
    assert fed.macro_impact is True


def test_partial_feed_failure_does_not_remove_other_public_sources():
    def opener(request, timeout):
        if "federalreserve" in request.full_url:
            raise TimeoutError("slow")
        if "sec.gov" in request.full_url:
            return Response(rss("SEC crypto market update", "Crypto asset rules", "sec"))
        return Response(b"<rss><channel></channel></rss>")

    result = PublicMarketNewsProvider(opener=opener).fetch_facts(
        None, (position("NVDA", "NVIDIA", "100"),)
    )

    assert result.status == "available"
    assert any(item.source == "SEC" for item in result.items)
