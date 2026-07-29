"""Provider-independent aggregation for the ARGOS daily flow."""

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Sequence, Tuple

from backend.daily.models import (
    AgendaEvent as AgendaEvent,
    ExternalDataResult,
    MarketEvent as MarketEvent,
)
from backend.daily.registry import build_default_registry
from backend.daily.cache import DailyCache
from backend.models import PortfolioPosition

PRIORITY_LEVELS = ("Alta", "Moderada", "Baixa")
_PRIORITY_SCORE = {"Alta": 3, "Moderada": 2, "Baixa": 1}
DAILY_LOOKBACK_HOURS = 48


def _position_terms(position: PortfolioPosition) -> Tuple[str, ...]:
    values = [position.identifier, position.asset_name]
    terms = {value.strip().upper() for value in values if value and value.strip()}
    expanded = set(terms)
    for term in terms:
        if term in {"ETH", "ETHB"} or "ETHEREUM" in term:
            expanded.update({"ETH", "ETHB", "ETHEREUM"})
        if term == "NVDA" or "NVIDIA" in term:
            expanded.update({"NVDA", "NVIDIA"})
    return tuple(expanded)


def _matching_assets(related_assets, positions: Sequence[PortfolioPosition]) -> Tuple[str, ...]:
    event_terms = {asset.strip().upper() for asset in related_assets if asset.strip()}
    matches = []
    for position in positions:
        # Only exact normalized aliases are direct relationships. Substring matching
        # would incorrectly connect funds and ETFs to their underlying themes.
        if event_terms.intersection(_position_terms(position)):
            label = position.identifier or position.asset_name
            if label and label not in matches:
                matches.append(label)
    return tuple(matches)


def _effective_priority(base_priority: str, has_portfolio_match: bool) -> str:
    if base_priority not in _PRIORITY_SCORE:
        raise ValueError(f"Prioridade inválida: {base_priority}. Use Alta, Moderada ou Baixa.")
    score = _PRIORITY_SCORE[base_priority] + int(has_portfolio_match)
    return PRIORITY_LEVELS[max(0, 3 - min(score, 3))]


class DailyContextService:
    """Build a prioritized context from normalized external data."""

    def __init__(
        self,
        events=None,
        agenda=None,
        registry=None,
        cache=None,
    ):
        self._events = tuple(events) if events is not None else None
        self._agenda = tuple(agenda) if agenda is not None else None
        self._registry = registry
        self._cache = cache

    def _load(self, kind, positions, reference):
        explicit = self._events if kind == "facts" else self._agenda
        if explicit is not None:
            return ExternalDataResult("available" if explicit else "empty", explicit, False)
        cache = self._cache or DailyCache()
        cached = cache.get_fresh(kind, reference)
        if cached is not None:
            return cached
        try:
            registry = self._registry or build_default_registry()
            result = getattr(registry, f"fetch_{kind}")(reference, positions)
        except Exception as exc:
            result = ExternalDataResult("unavailable", (), False, str(exc))
        if result.status in {"available", "empty"}:
            cache.put(kind, result, reference)
            return result
        stale = cache.get_last_valid(kind)
        if stale is not None:
            return ExternalDataResult("unavailable", stale.items, True, result.error)
        return result

    def generate(self, positions: Iterable[PortfolioPosition], now: Optional[datetime] = None) -> Dict:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        positions = tuple(positions)
        facts_result = self._load("facts", positions, reference)
        agenda_result = self._load("agenda", positions, reference)
        cutoff = reference - timedelta(hours=DAILY_LOOKBACK_HOURS)
        facts = []
        for event in facts_result.items:
            occurred_at = event.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            if not cutoff <= occurred_at <= reference:
                continue
            matches = _matching_assets(event.related_assets, positions)
            priority = _effective_priority(event.priority, bool(matches))
            if matches:
                context, context_type = "Relacionado à carteira: " + ", ".join(matches), "portfolio"
            elif event.macro_impact:
                context = "Impacto macro para as carteiras" if positions else "Contexto macro geral de mercado"
                context_type = "macro"
            else:
                context, context_type = "Contexto geral de mercado", "general"
            facts.append({
                "id": event.identifier, "title": event.title, "category": event.category,
                "source": event.source, "occurred_at": occurred_at.isoformat(),
                "priority": priority, "base_priority": event.priority, "summary": event.summary,
                "related_assets": list(event.related_assets), "matched_portfolio_assets": list(matches),
                "context": context, "context_type": context_type, "_time": occurred_at,
            })
        facts.sort(key=lambda item: (-_PRIORITY_SCORE[item["priority"]], -item["_time"].timestamp()))
        for item in facts:
            item.pop("_time")
        facts = facts[:5]

        agenda = []
        for event in agenda_result.items:
            scheduled_at = event.scheduled_at
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            if scheduled_at < reference:
                continue
            matches = _matching_assets(event.related_assets, positions)
            agenda.append({
                "id": event.identifier, "title": event.title, "event_type": event.category,
                "category": event.category, "scheduled_at": scheduled_at.isoformat(),
                "source": event.source, "importance": event.importance,
                "time_explicit": event.time_explicit,
                "related_assets": list(event.related_assets), "matched_portfolio_assets": list(matches),
                "scope": "portfolio" if matches else "general",
                "summary": ("Relacionado à carteira: " + ", ".join(matches)) if matches else "Evento geral de mercado",
                "_time": scheduled_at,
            })
        agenda.sort(key=lambda item: (not bool(item["matched_portfolio_assets"]), item["_time"]))
        for item in agenda:
            item.pop("_time")
        return {
            "generated_at": reference.isoformat(),
            "lookback_hours": DAILY_LOOKBACK_HOURS,
            "has_portfolio_context": bool(positions), "facts": facts, "agenda": agenda,
            "sources": {
                "facts": {"status": facts_result.status if facts_result.status == "unavailable" or facts else "empty", "cached": facts_result.cached, "error": facts_result.error},
                "agenda": {"status": agenda_result.status if agenda_result.status == "unavailable" or agenda else "empty", "cached": agenda_result.cached, "error": agenda_result.error},
            },
        }
