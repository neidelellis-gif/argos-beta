"""External providers and normalization for market facts and calendars."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Iterable, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.config.settings import get_setting
from backend.models import PortfolioPosition


@dataclass(frozen=True)
class ExternalDataResult:
    status: str
    items: Tuple[Any, ...]
    cached: bool = False
    error: Optional[str] = None


class ExternalDailyProvider:
    """Replaceable contract consumed by DailyContextService."""
    name = "external"

    def fetch_facts(self, now, positions):
        raise NotImplementedError

    def fetch_agenda(self, now, positions):
        raise NotImplementedError


def _parse_time(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if not value:
        return None
    normalized = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.strptime(str(value)[:10], "%Y-%m-%d")
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


class FinnhubDailyProvider(ExternalDailyProvider):
    """Finnhub implementation; all responses are normalized at this boundary."""
    name = "Finnhub"
    base_url = "https://finnhub.io/api/v1"

    def __init__(self, api_key=None, opener=None):
        self.api_key = api_key if api_key is not None else get_setting("FINNHUB_API_KEY")
        self._opener = opener or urlopen

    def _get(self, path, **params):
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY não configurada")
        params["token"] = self.api_key
        with self._opener(f"{self.base_url}/{path}?{urlencode(params)}", timeout=10) as response:
            return json.load(response)

    @staticmethod
    def normalize_news(rows):
        from backend.daily.context_service import MarketEvent
        events = []
        for row in rows or ():
            occurred = _parse_time(row.get("datetime"))
            title = str(row.get("headline") or "").strip()
            if not occurred or not title:
                continue
            symbol = str(row.get("related") or "").upper().strip()
            text = f"{title} {row.get('summary', '')}".upper()
            if symbol == "NVDA" or "NVIDIA" in text:
                assets, category = ("NVDA", "NVIDIA"), "Tecnologia"
            elif symbol in {"ETH", "ETHB"} or "ETHEREUM" in text:
                assets, category = ("ETH", "ETHB", "ETHEREUM"), "Criptoativos"
            else:
                assets = (symbol,) if symbol else ()
                category = "Geopolítica" if any(word in text for word in ("WAR", "SANCTION", "CONFLICT")) else "Mercados"
            priority = "Alta" if row.get("category") in {"top news", "merger"} else "Moderada"
            events.append(MarketEvent(
                str(row.get("id") or row.get("url") or f"news-{int(occurred.timestamp())}"),
                title, category, str(row.get("source") or "Finnhub"), occurred, priority,
                str(row.get("summary") or title).strip(), assets, category == "Macroeconomia",
            ))
        return tuple(events)

    @staticmethod
    def normalize_calendar(economic, earnings, dividends=()):
        from backend.daily.context_service import AgendaEvent
        events = []
        for row in (economic or {}).get("economicCalendar", economic or ()):
            raw_time = row.get("time") or row.get("date")
            scheduled = _parse_time(raw_time)
            title = str(row.get("event") or "").strip()
            if not scheduled or not title:
                continue
            lowered = title.lower()
            category = "Bancos centrais" if any(x in lowered for x in ("rate", "central bank", "fomc")) else "Inflação" if any(x in lowered for x in ("inflation", "cpi", "ppi")) else "Emprego" if any(x in lowered for x in ("employment", "payroll", "jobless")) else "PIB" if "gdp" in lowered else "Macroeconomia"
            importance = {1: "Baixa", 2: "Moderada", 3: "Alta"}.get(row.get("impact"), "Moderada")
            events.append(AgendaEvent(
                f"economic-{row.get('date')}-{title}", title, category,
                scheduled, "Finnhub", importance, (),
                bool(row.get("time") or "T" in str(raw_time)),
            ))
        for row in (earnings or {}).get("earningsCalendar", earnings or ()):
            scheduled = _parse_time(row.get("date"))
            symbol = str(row.get("symbol") or "").upper()
            if scheduled and symbol:
                events.append(AgendaEvent(
                    f"earnings-{symbol}-{row.get('date')}",
                    f"Resultados corporativos — {symbol}", "Resultados",
                    scheduled, "Finnhub", "Moderada", (symbol,), False,
                ))
        for row in dividends or ():
            scheduled = _parse_time(row.get("date") or row.get("payDate"))
            symbol = str(row.get("symbol") or "").upper()
            if scheduled and symbol:
                events.append(AgendaEvent(
                    f"dividend-{symbol}-{scheduled.date().isoformat()}",
                    f"Dividendo — {symbol}", "Dividendos", scheduled,
                    "Finnhub", "Moderada", (symbol,), False,
                ))
        return tuple(events)

    def fetch_facts(self, now, positions):
        rows = self._get("news", category="general", minId=0)
        items = self.normalize_news(rows)
        return ExternalDataResult("available" if items else "empty", items)

    def fetch_agenda(self, now, positions):
        end = (now + timedelta(days=30)).date().isoformat()
        start = now.date().isoformat()
        economic = self._get("calendar/economic", **{"from": start, "to": end})
        earnings = self._get("calendar/earnings", **{"from": start, "to": end})
        symbols = sorted({
            position.identifier.strip().upper()
            for position in positions
            if position.identifier and position.identifier.strip()
        })
        dividends = []
        for symbol in symbols[:25]:
            rows = self._get("stock/dividend2", symbol=symbol, **{"from": start, "to": end})
            for row in rows or ():
                dividends.append({**row, "symbol": symbol})
        items = self.normalize_calendar(economic, earnings, dividends)
        return ExternalDataResult("available" if items else "empty", items)
