from datetime import date, datetime, timezone
from inspect import getsource, signature

import backend.daily.orchestrator as orchestrator_module
from backend.daily.context_service import PRIORITY_LEVELS
from backend.daily.experience import PANORAMA_TOPICS, build_daily_experience
from backend.daily.orchestrator import DailyOrchestrator
from backend.daily.transformations import build_analyses, build_priorities


NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
CURRENT_DATE = date(2026, 7, 28)


def fact(identifier="official-fact"):
    return {
        "id": identifier,
        "title": f"Official fact {identifier}",
        "category": "Mercados",
        "source": "Official source",
        "occurred_at": "2026-07-28T10:00:00+00:00",
        "priority": "Alta",
        "base_priority": "Alta",
        "summary": f"Official summary {identifier}",
        "related_assets": [],
        "matched_portfolio_assets": [],
        "context": "Contexto geral",
        "context_type": "macro",
    }


def agenda(identifier="official-agenda"):
    return {"id": identifier, "title": f"Official agenda {identifier}"}


class StubContextService:
    def __init__(self, facts=None, agenda_items=None):
        self.facts = list(facts or [])
        self.agenda = list(agenda_items or [])
        self.calls = []

    def generate(self, positions, now=None):
        self.calls.append((positions, now))
        return {
            "generated_at": (now or NOW).isoformat(),
            "lookback_hours": 24,
            "has_portfolio_context": bool(positions),
            "facts": [dict(item) for item in self.facts],
            "agenda": [dict(item) for item in self.agenda],
            "sources": {
                "facts": {"status": "available", "cached": False, "error": None},
                "agenda": {"status": "available", "cached": False, "error": None},
            },
        }


def test_build_has_the_expanded_public_signature():
    parameters = signature(DailyOrchestrator.build).parameters

    assert tuple(parameters) == ("self", "positions", "current_date", "now")
    assert parameters["positions"].default == ()
    assert parameters["current_date"].default is None
    assert parameters["now"].default is None


def test_orchestrator_has_no_experience_dependency():
    source = getsource(orchestrator_module)

    assert "daily.experience" not in source
    assert "build_daily_" not in source


def test_orchestrator_reuses_the_shared_transformations():
    assert orchestrator_module.build_priorities is build_priorities
    assert orchestrator_module.build_analyses is build_analyses


def test_build_forwards_positions_current_date_and_now():
    positions = (object(),)
    service = StubContextService([fact()])

    daily = DailyOrchestrator(service).build(positions, CURRENT_DATE, NOW)

    assert service.calls == [(positions, NOW)]
    assert daily["generated_for"] == CURRENT_DATE.isoformat()
    assert daily["generated_at"] == NOW.isoformat()
    assert daily["context_scope"] == "portfolio"


def test_build_produces_the_complete_daily_contract():
    official_fact = fact()
    official_agenda = agenda()

    daily = DailyOrchestrator(
        StubContextService([official_fact], [official_agenda])
    ).build(current_date=CURRENT_DATE, now=NOW)

    assert set(daily) == {
        "generated_for",
        "generated_at",
        "lookback_hours",
        "context_scope",
        "important_facts",
        "priorities",
        "analyses",
        "global_overview",
        "market_agenda",
        "sources",
        "empty_states",
        "contracts",
    }
    assert daily["generated_for"] == "2026-07-28"
    assert daily["context_scope"] == "general"
    assert daily["important_facts"] == [official_fact]
    assert daily["priorities"] == build_priorities([official_fact])
    assert daily["analyses"] == build_analyses([official_fact])
    assert tuple(item["topic"] for item in daily["global_overview"]) == PANORAMA_TOPICS
    assert daily["market_agenda"] == [official_agenda]
    assert set(daily["sources"]) == {"facts", "agenda"}
    assert set(daily["empty_states"]) == {"important_facts", "market_agenda"}
    assert daily["contracts"]["priority_levels"] == list(PRIORITY_LEVELS)
    assert daily["contracts"]["panorama_topics"] == list(PANORAMA_TOPICS)
    assert "agenda_event_types" in daily["contracts"]


def test_build_matches_build_daily_experience_for_the_same_input():
    positions = (object(),)
    orchestrator_service = StubContextService([fact()], [agenda()])
    experience_service = StubContextService([fact()], [agenda()])

    orchestrated = DailyOrchestrator(orchestrator_service).build(
        positions, CURRENT_DATE, NOW
    )
    existing = build_daily_experience(
        positions, CURRENT_DATE, NOW, experience_service
    )

    assert orchestrated == existing
    assert orchestrator_service.calls == experience_service.calls


def test_build_calls_context_service_only_once():
    service = StubContextService([fact()])

    DailyOrchestrator(service).build(current_date=CURRENT_DATE, now=NOW)

    assert service.calls == [((), NOW)]


def test_build_uses_the_official_priorities_transformation(monkeypatch):
    facts = [fact("first"), fact("second")]
    expected = [{"official": "priorities"}]
    calls = []

    def official_transformation(received_facts):
        calls.append(received_facts)
        return expected

    monkeypatch.setattr(
        orchestrator_module,
        "build_priorities",
        official_transformation,
    )

    daily = DailyOrchestrator(StubContextService(facts)).build(
        current_date=CURRENT_DATE,
        now=NOW,
    )

    assert calls == [daily["important_facts"]]
    assert daily["priorities"] is expected


def test_build_uses_the_official_analyses_transformation(monkeypatch):
    facts = [fact("first"), fact("second")]
    expected = [{"official": "analyses"}]
    calls = []

    def official_transformation(received_facts):
        calls.append(received_facts)
        return expected

    monkeypatch.setattr(
        orchestrator_module,
        "build_analyses",
        official_transformation,
    )

    daily = DailyOrchestrator(StubContextService(facts)).build(
        current_date=CURRENT_DATE,
        now=NOW,
    )

    assert calls == [daily["important_facts"]]
    assert daily["analyses"] is expected


def test_shared_transformations_preserve_order_and_limits():
    facts = [fact("first"), fact("second"), fact("third"), fact("fourth")]

    daily = DailyOrchestrator(StubContextService(facts)).build(
        current_date=CURRENT_DATE,
        now=NOW,
    )

    assert [item["id"] for item in daily["priorities"]] == [
        "first", "second", "third",
    ]
    assert [item["id"] for item in daily["analyses"]] == ["first", "second"]


def test_build_without_arguments_remains_compatible(monkeypatch):
    service = StubContextService()
    monkeypatch.setattr(orchestrator_module, "date", type(
        "FixedDate",
        (),
        {"today": staticmethod(lambda: CURRENT_DATE)},
    ))

    daily = DailyOrchestrator(service).build()

    assert service.calls == [((), None)]
    assert daily["generated_for"] == CURRENT_DATE.isoformat()
    assert daily["context_scope"] == "general"


def test_build_returns_independent_lists_between_calls():
    service = StubContextService([fact()], [agenda()])
    orchestrator = DailyOrchestrator(service)

    first = orchestrator.build(current_date=CURRENT_DATE, now=NOW)
    second = orchestrator.build(current_date=CURRENT_DATE, now=NOW)

    list_paths = (
        "important_facts",
        "priorities",
        "analyses",
        "global_overview",
        "market_agenda",
    )
    assert first == second
    assert all(first[name] is not second[name] for name in list_paths)
    assert first["contracts"]["priority_levels"] is not second["contracts"]["priority_levels"]
    assert first["contracts"]["panorama_topics"] is not second["contracts"]["panorama_topics"]
    assert first["contracts"]["agenda_event_types"] is not second["contracts"]["agenda_event_types"]
