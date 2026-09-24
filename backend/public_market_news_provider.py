"""Credential-free public market news for the ARGOS daily context."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import re
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from backend.daily.models import ExternalDataResult, MarketEvent
from backend.daily.providers import ExternalDailyProvider


FED_MONETARY_RSS = "https://www.federalreserve.gov/feeds/press_monetary.xml"
SEC_PRESS_RSS = "https://www.sec.gov/news/pressreleases.rss"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

_LOW_VALUE_MARKET_PATTERNS = (
    "interactive stock chart",
    "stock price, news, quote and history",
    "stock price news quote and history",
    "option chain",
    "options chain",
    "historical data",
    "historical prices",
    "price chart",
    "quote overview",
)


class PublicMarketNewsProvider(ExternalDailyProvider):
    """Read public feeds without requiring any customer credentials."""

    name = "PublicMarketNews"

    def __init__(self, opener=None, timeout_seconds: float = 2.0, max_portfolio_terms: int = 12):
        self._opener = opener or urlopen
        self._timeout_seconds = float(timeout_seconds)
        self._max_portfolio_terms = int(max_portfolio_terms)

    def fetch_facts(self, now, positions):
        events = []
        errors = []
        reference = now or datetime.now(timezone.utc)
        cutoff = reference.astimezone(timezone.utc) - timedelta(hours=48)

        sources = [
            (FED_MONETARY_RSS, "Federal Reserve", True),
            (SEC_PRESS_RSS, "SEC", False),
        ]
        portfolio_url = self._portfolio_news_url(tuple(positions))
        if portfolio_url:
            sources.append((portfolio_url, "Google News", False))

        for url, source, macro in sources:
            try:
                xml_bytes = self._read(url)
                events.extend(
                    event
                    for event in self._parse_feed(xml_bytes, source, tuple(positions), macro)
                    if cutoff <= event.occurred_at <= reference.astimezone(timezone.utc)
                )
            except Exception as exc:
                errors.append(f"{source}: {type(exc).__name__}")

        if events:
            unique = {}
            for event in events:
                unique[(event.title.casefold(), event.occurred_at)] = event
            return ExternalDataResult("available", tuple(unique.values()))
        if errors:
            return ExternalDataResult("unavailable", (), error="; ".join(errors))
        return ExternalDataResult("empty", ())

    def fetch_agenda(self, now, positions):
        return ExternalDataResult("empty", ())

    def _read(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": "ARGOS/1.0"})
        with self._opener(request, timeout=self._timeout_seconds) as response:
            return response.read()

    def _portfolio_news_url(self, positions) -> str | None:
        ranked = sorted(
            positions,
            key=lambda item: (-(float(item.market_value) if item.market_value is not None else 0.0),
                              (item.identifier or item.asset_name or "").casefold()),
        )
        terms = []
        for position in ranked:
            value = (position.identifier or "").strip().upper()
            if value and value not in terms:
                terms.append(value)
            if len(terms) >= self._max_portfolio_terms:
                break
        if not terms:
            return None
        query = " OR ".join(terms) + " when:1d"
        return (
            f"{GOOGLE_NEWS_RSS}?q={quote_plus(query)}"
            "&hl=en-US&gl=US&ceid=US:en"
        )

    def _parse_feed(self, payload: bytes, source: str, positions, macro: bool):
        root = ET.fromstring(payload)
        events = []
        for item in root.findall(".//item"):
            title = self._text(item.findtext("title"))
            description = self._text(item.findtext("description"))
            published = self._published(item.findtext("pubDate"))
            if not title or published is None:
                continue
            text = f"{title} {description}"
            if source == "Google News" and self._is_low_value_market_page(text):
                continue
            related = self._related_assets(text, positions)
            category = self._category(source, text)
            # Macro facts remain portfolio-level context. Do not turn USD into
            # a claim that every USD-denominated position is directly affected.
            if source == "Federal Reserve" and not related:
                related = ()
            events.append(MarketEvent(
                identifier=self._identifier(source, item.findtext("guid"), title, published),
                title=title,
                category=category,
                source=source,
                occurred_at=published,
                priority="Alta" if source == "Federal Reserve" else "Moderada",
                summary=description or title,
                related_assets=related,
                macro_impact=macro,
            ))
        return tuple(events)

    @staticmethod
    def _is_low_value_market_page(text: str) -> bool:
        normalized = " ".join(text.casefold().split())
        return any(pattern in normalized for pattern in _LOW_VALUE_MARKET_PATTERNS)

    @staticmethod
    def _related_assets(text: str, positions) -> tuple[str, ...]:
        normalized = f" {re.sub(r'[^A-Z0-9]+', ' ', text.upper())} "
        matches = []
        for position in positions:
            identifier = (position.identifier or "").strip().upper()
            name = (position.asset_name or "").strip().upper()
            identifier_match = identifier and f" {identifier} " in normalized
            name_match = len(name) >= 4 and name in text.upper()
            if identifier_match or name_match:
                label = position.identifier or position.asset_name
                if label and label not in matches:
                    matches.append(label)
        return tuple(matches)

    @staticmethod
    def _category(source: str, text: str) -> str:
        upper = text.upper()
        if source == "Federal Reserve":
            return "Macroeconomia"
        if source == "SEC":
            return "Regulação"
        if any(word in upper for word in ("BITCOIN", "CRYPTO", "ETHEREUM")):
            return "Criptoativos"
        if any(word in upper for word in ("WAR", "SANCTION", "CONFLICT")):
            return "Geopolítica"
        return "Mercados"

    @staticmethod
    def _published(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _text(value: str | None) -> str:
        if not value:
            return ""
        plain = re.sub(r"<[^>]+>", " ", unescape(value))
        return " ".join(plain.split())

    @staticmethod
    def _identifier(source: str, guid: str | None, title: str, published: datetime) -> str:
        raw = guid.strip() if isinstance(guid, str) and guid.strip() else title
        compact = re.sub(r"[^a-z0-9]+", "-", raw.casefold()).strip("-")[:80]
        return f"{source.casefold().replace(' ', '-')}-{published:%Y%m%d%H%M}-{compact}"
