"""Merge professional market news into the canonical ARGOS fact stream."""

from datetime import datetime, timezone
from typing import Iterable

from backend.daily.models import MarketEvent
from backend.daily.providers import ExternalDailyProvider
from backend.important_facts import FactCandidate, FactCategory, FactImportance
from backend.models import PortfolioPosition


_PRIORITY = {
    "Alta": FactImportance.HIGH,
    "Moderada": FactImportance.MEDIUM,
    "Baixa": FactImportance.LOW,
}

_CATEGORY = {
    "Geopolítica": FactCategory.GEOPOLITICS,
    "Macroeconomia": FactCategory.ECONOMY,
    "Economia": FactCategory.ECONOMY,
    "Regulação": FactCategory.REGULATION,
    "Corporativo": FactCategory.CORPORATE,
    "Tecnologia": FactCategory.MARKETS,
    "Criptoativos": FactCategory.MARKETS,
    "Mercados": FactCategory.MARKETS,
}


def _canonical_fact(event: MarketEvent) -> FactCandidate:
    importance = _PRIORITY.get(event.priority, FactImportance.MEDIUM)
    return FactCandidate(
        id=f"professional-{event.identifier}",
        title=event.title,
        description=event.summary,
        source=event.source,
        published_at=event.occurred_at,
        importance=importance,
        urgency=importance,
        category=_CATEGORY.get(event.category, FactCategory.OTHER),
        related_assets=tuple(event.related_assets),
    )


def load_market_context_facts(
    official_facts: Iterable[FactCandidate],
    positions: Iterable[PortfolioPosition],
    provider: ExternalDailyProvider,
    now: datetime | None = None,
) -> tuple[FactCandidate, ...]:
    """Keep official facts first and append normalized professional facts safely."""
    official = tuple(official_facts)
    reference = now or datetime.now(timezone.utc)
    try:
        result = provider.fetch_facts(reference, tuple(positions))
    except Exception:
        return official
    if result.status != "available":
        return official

    merged = list(official)
    seen = {item.id.casefold() for item in official}
    for event in result.items:
        if not isinstance(event, MarketEvent):
            continue
        fact = _canonical_fact(event)
        key = fact.id.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(fact)
    return tuple(merged)
