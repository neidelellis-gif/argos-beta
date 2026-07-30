from dataclasses import FrozenInstanceError
from datetime import date
import json

import pytest

from backend.daily_facts_engine import DailyFactsEngine
from backend.market_agenda_engine import MarketAgendaEngine
from backend.market_data_loader import MarketDataLoader, MarketDataValidationError
from backend.official_portfolios import OfficialPortfolioLoader


def source(collection, rows):
    return {
        "source_id": "OFFICIAL-1", "source_name": "Banco Central",
        "source_type": "BANCO_CENTRAL", "reference_date": "2026-07-30",
        "collected_at": "2026-07-30T12:00:00Z", "data_version": "1.0",
        collection: rows,
    }


def fact(**changes):
    value = {
        "fact_id": "fact-1", "title": "Fato oficial", "description": "Evidência oficial.",
        "category": "ECONOMY", "source": "OFFICIAL-1", "reference_date": "2026-07-30",
        "importance": "HIGH", "related_assets": ["LFT-2029"], "related_sectors": [],
        "related_currencies": ["BRL"], "related_institutions": [],
    }
    value.update(changes)
    return value


def event(**changes):
    value = {
        "event_id": "event-1", "event_type": "CENTRAL_BANK", "title": "Agenda oficial",
        "event_date": "2026-08-01", "event_time": None, "timezone": None, "all_day": True,
        "institution": "Banco Central", "asset_identifiers": ["LFT-2029"], "asset_names": [],
        "asset_classes": ["FIXED_INCOME"], "sectors": [], "currencies": ["BRL"],
        "markets": ["BRAZIL"], "country": "BR", "importance": "HIGH",
        "source_name": "Banco Central", "source_reference": "calendar-1", "description": "Evento oficial.",
    }
    value.update(changes)
    return value


def repository(tmp_path, facts=None, events=None):
    (tmp_path / "facts").mkdir(); (tmp_path / "agenda").mkdir()
    (tmp_path / "facts" / "facts.json").write_text(json.dumps(source("facts", facts or [fact()])))
    (tmp_path / "agenda" / "agenda.json").write_text(json.dumps(source("events", events or [event()])))
    return MarketDataLoader(tmp_path)


def test_loads_immutable_canonical_facts_and_agenda(tmp_path):
    loaded = repository(tmp_path).load()
    assert loaded.facts[0].fact_id == "fact-1"
    assert loaded.facts[0].reference_date == date(2026, 7, 30)
    assert loaded.agenda[0].event_id == "event-1"
    assert isinstance(loaded.facts, tuple) and isinstance(loaded.agenda, tuple)
    with pytest.raises(FrozenInstanceError):
        loaded.sources[0].source_name = "alterada"  # type: ignore[misc]


@pytest.mark.parametrize(("facts", "events", "diagnostic"), [
    ([fact(), fact()], None, "facts.duplicates"),
    (None, [event(), event()], "agenda.duplicates"),
    ([fact(reference_date="30/07/2026")], None, "facts.invalid_date"),
    ([fact(category="NEWS")], None, "facts.invalid_category"),
    ([fact(related_assets=["ativo inválido"])], None, "facts.invalid_assets"),
])
def test_rejects_invalid_official_data(tmp_path, facts, events, diagnostic):
    with pytest.raises(MarketDataValidationError) as raised:
        repository(tmp_path, facts, events).load()
    assert raised.value.diagnostic_id == diagnostic


def test_official_repository_runs_unchanged_engines_with_official_portfolios():
    market = MarketDataLoader().load()
    positions = OfficialPortfolioLoader().load_positions()
    facts = DailyFactsEngine().generate(positions, market.facts)
    agenda = MarketAgendaEngine().generate(market.agenda, positions, date(2026, 7, 30))
    assert facts and facts[0]["id"] == "bcb-focus-2026-07-30"
    assert agenda and agenda[0]["id"] == "agenda-bcb-copom-2026-08-05"
