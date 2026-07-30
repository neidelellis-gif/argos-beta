import csv
import io
import json

import pytest

from backend.market_agenda import (
    CSV_FIELDS, MarketAgendaImportance, MarketAgendaValidationError,
    import_market_agenda,
)


def event(**changes):
    value = {
        "event_id": "fed-1", "event_type": "CENTRAL_BANK", "title": "Decisão de juros",
        "event_date": "2026-07-30", "event_time": "14:00", "timezone": "America/New_York",
        "all_day": False, "institution": "Federal Reserve", "asset_identifiers": [],
        "asset_names": [], "asset_classes": ["FIXED_INCOME"], "sectors": [],
        "currencies": ["USD"], "markets": ["UNITED_STATES"], "country": "US",
        "importance": "HIGH", "source_name": "Federal Reserve",
        "source_reference": "official-calendar", "description": "Evento oficial.",
    }
    value.update(changes)
    return value


def encoded(*events):
    return json.dumps({"events": list(events)}).encode()


def test_imports_valid_json_and_normalizes_compatibility_importance():
    events = import_market_agenda("test.json", encoded(event(importance="CRITICAL")))
    assert events[0].importance is MarketAgendaImportance.HIGH
    assert events[0].asset_classes == ("FIXED_INCOME",)


def test_imports_valid_csv_collections():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    row = event(all_day="false", asset_identifiers="NVDA|AMD", asset_names="",
                asset_classes="EQUITY", sectors="", currencies="USD", markets="US")
    writer.writerow(row)  # pyright: ignore[reportArgumentType]
    result = import_market_agenda("test.csv", output.getvalue().encode())
    assert result[0].asset_identifiers == ("NVDA", "AMD")


@pytest.mark.parametrize("change", [
    {"event_type": "NEWS"}, {"importance": "URGENT"}, {"event_date": "30/07/2026"},
    {"event_time": "25:00"}, {"timezone": "EST"}, {"source_name": ""},
    {"title": "x" * 201}, {"description": "x" * 1001},
    {"all_day": True, "event_time": "14:00"},
])
def test_rejects_invalid_events(change):
    with pytest.raises(MarketAgendaValidationError):
        import_market_agenda("test.json", encoded(event(**change)))


def test_rejects_empty_duplicate_and_excessive_files():
    with pytest.raises(MarketAgendaValidationError):
        import_market_agenda("test.json", b"")
    with pytest.raises(MarketAgendaValidationError):
        import_market_agenda("test.json", encoded(event(), event()))
    with pytest.raises(MarketAgendaValidationError):
        import_market_agenda("test.json", encoded(*(event(event_id=str(i)) for i in range(1001))))
