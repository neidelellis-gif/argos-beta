"""Side-effect-free serializers for canonical market agenda events."""

from backend.market_agenda import MarketAgendaEvent


def serialize_market_agenda_event(event: MarketAgendaEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id, "event_type": event.event_type.value,
        "title": event.title, "event_date": event.event_date.isoformat(),
        "event_time": None if event.event_time is None else event.event_time.strftime("%H:%M"),
        "timezone": event.timezone, "all_day": event.all_day,
        "institution": event.institution,
        "asset_identifiers": list(event.asset_identifiers), "asset_names": list(event.asset_names),
        "asset_classes": list(event.asset_classes), "sectors": list(event.sectors),
        "currencies": list(event.currencies), "markets": list(event.markets),
        "country": event.country, "importance": event.importance.value,
        "source_name": event.source_name, "source_reference": event.source_reference,
        "description": event.description,
    }


def serialize_market_agenda(events: tuple[MarketAgendaEvent, ...]) -> list[dict[str, object]]:
    return [serialize_market_agenda_event(event) for event in events]
