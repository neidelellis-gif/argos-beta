from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.market_agenda import validate_market_agenda_event
from backend.market_agenda_engine import MarketAgendaEngine
from backend.models import PortfolioOwner, PortfolioPosition
from tests.test_market_agenda import event


def position():
    return PortfolioPosition(
        institution="UBS", owner=PortfolioOwner.JOLIKA, account=None,
        asset_class="EQUITY", asset_subclass=None, asset_name="NVIDIA", identifier="NVDA",
        identifier_type="TICKER", quantity=Decimal("1"), unit_price=None, market_value=None,
        currency="USD", portfolio_weight=None, reference_date=None, source_file="test.csv",
    )


def test_empty_portfolio_and_irrelevant_events_are_empty():
    engine = MarketAgendaEngine()
    assert engine.generate((), (), date(2026, 7, 30)) == ()
    other = validate_market_agenda_event(event(asset_classes=[], currencies=[], markets=[], country=None))
    assert engine.generate((other,), (position(),), date(2026, 7, 30)) == ()


def test_selects_direct_and_broad_matches_with_exact_public_internal_fields():
    direct = validate_market_agenda_event(event(asset_identifiers=["NVDA"]))
    result = MarketAgendaEngine().generate((direct,), (position(),), date(2026, 7, 30))
    assert result[0]["affected_assets"] == ["NVDA"]
    assert set(result[0]) == {"id", "event_type", "importance", "title", "description",
        "event_date", "event_time", "timezone", "all_day", "affected_assets", "source_name"}


def test_window_order_deduplication_limit_clock_and_immutability():
    events = tuple(validate_market_agenda_event(event(
        event_id=str(index), title=f"Evento {index:02}", event_date="2026-07-30",
        asset_identifiers=["NVDA"], source_reference=str(index))) for index in range(12))
    past = validate_market_agenda_event(event(event_id="past", event_date="2026-07-29"))
    late = validate_market_agenda_event(event(event_id="late", event_date="2026-08-07"))
    duplicate = validate_market_agenda_event(event(event_id="duplicate", title="Evento 00",
        asset_identifiers=["NVDA"], source_reference="different"))
    positions = (position(),)
    before_events, before_positions = deepcopy(events), deepcopy(positions)
    engine = MarketAgendaEngine(clock=lambda: datetime(2026, 7, 30, tzinfo=timezone.utc))
    result = engine.generate(events + (past, late, duplicate), positions, None)
    assert len(result) == 10
    assert [item["title"] for item in result] == [f"Evento {i:02}" for i in range(10)]
    assert events == before_events and positions == before_positions
