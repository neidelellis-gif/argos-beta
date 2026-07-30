"""Select relevant structured market events for the daily experience."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone

from backend.market_agenda import MarketAgendaEvent, MarketAgendaImportance, MarketAgendaEventType
from backend.models import PortfolioPosition


_GENERAL_TYPES = {
    MarketAgendaEventType.CENTRAL_BANK, MarketAgendaEventType.MACROECONOMIC,
    MarketAgendaEventType.REGULATORY, MarketAgendaEventType.MARKET_HOLIDAY,
}
_IMPORTANCE = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _normalized(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


class MarketAgendaEngine:
    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._clock = clock

    def generate(
        self, events: Iterable[MarketAgendaEvent], positions: Iterable[PortfolioPosition],
        reference_date: date | None,
    ) -> tuple[dict[str, object], ...]:
        event_values, position_values = tuple(events), tuple(positions)
        reference = reference_date or self._clock().date()
        end = reference + timedelta(days=7)
        candidates = [event for event in event_values if reference <= event.event_date <= end]
        candidates = self._deduplicate(candidates)
        output: list[dict[str, object]] = []
        for event in candidates:
            affected, relevant = self._relevance(event, position_values)
            if relevant:
                output.append({
                    "id": f"agenda-{event.event_id}", "event_type": event.event_type.value,
                    "importance": event.importance.value, "title": event.title,
                    "description": event.description or "", "event_date": event.event_date.isoformat(),
                    "event_time": None if event.event_time is None else event.event_time.strftime("%H:%M"),
                    "timezone": event.timezone, "all_day": event.all_day,
                    "affected_assets": list(affected), "source_name": event.source_name,
                })
        output.sort(key=lambda item: (
            item["event_date"], item["event_time"] is None, item["event_time"] or "",
            _IMPORTANCE[str(item["importance"])], _normalized(str(item["title"])), item["id"],
        ))
        return tuple(output[:10])

    @staticmethod
    def _relevance(event: MarketAgendaEvent, positions: tuple[PortfolioPosition, ...]) -> tuple[tuple[str, ...], bool]:
        affected = []
        broad_match = False
        for position in positions:
            identifier = _normalized(position.identifier)
            name = _normalized(position.asset_name)
            direct = (
                identifier and identifier in {_normalized(value) for value in event.asset_identifiers}
            ) or (name and name in {_normalized(value) for value in event.asset_names})
            other = any((
                _normalized(position.asset_class) in {_normalized(value) for value in event.asset_classes},
                _normalized(position.currency) in {_normalized(value) for value in event.currencies},
                _normalized(position.institution) in {_normalized(value) for value in (event.institution,)},
                _normalized(position.asset_subclass) in {_normalized(value) for value in event.sectors},
                _normalized(getattr(position, "market", None)) in {_normalized(value) for value in event.markets},
                _normalized(getattr(position, "country", None)) == _normalized(event.country) and bool(event.country),
            ))
            if direct:
                label = position.identifier or position.asset_name
                if label and label not in affected:
                    affected.append(label)
            broad_match = broad_match or other
        direct_event = bool(affected)
        general = event.importance is MarketAgendaImportance.HIGH and event.event_type in _GENERAL_TYPES and broad_match
        return tuple(affected), direct_event or broad_match or general

    @staticmethod
    def _deduplicate(events: list[MarketAgendaEvent]) -> list[MarketAgendaEvent]:
        def quality(event: MarketAgendaEvent) -> tuple[int, int, str]:
            filled = sum(value not in (None, "", ()) for value in event.__dict__.values())
            return (_IMPORTANCE[event.importance.value], -filled, event.event_id)
        selected: list[MarketAgendaEvent] = []
        for event in sorted(events, key=quality):
            title_key = (event.event_date, event.event_time, _normalized(event.title))
            source_key = (_normalized(event.source_name), _normalized(event.source_reference))
            if any(
                _normalized(item.event_id) == _normalized(event.event_id)
                or (item.event_date, item.event_time, _normalized(item.title)) == title_key
                or (_normalized(item.source_name), _normalized(item.source_reference)) == source_key
                for item in selected
            ):
                continue
            selected.append(event)
        return selected
