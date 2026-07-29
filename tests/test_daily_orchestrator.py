import backend.daily.orchestrator as orchestrator_module
from backend.daily.orchestrator import DailyOrchestrator


class StubContextService:
    def __init__(self, facts, agenda=()):
        self.facts = facts
        self.agenda = agenda
        self.calls = []

    def generate(self, positions):
        self.calls.append(positions)
        return {"facts": self.facts, "agenda": self.agenda}


def fact(
    identifier,
    priority="Alta",
    context="Contexto geral",
    context_type="macro",
):
    return {
        "id": identifier,
        "title": f"Official fact {identifier}",
        "priority": priority,
        "context": context,
        "summary": f"Official summary {identifier}",
        "matched_portfolio_assets": [],
        "occurred_at": "2026-07-28T10:00:00+00:00",
        "context_type": context_type,
    }


def agenda(identifier):
    return {"id": identifier, "title": f"Official agenda {identifier}"}


def test_build_creates_the_daily_structure():
    official_fact = fact("official-fact")
    official_agenda = agenda("official-agenda")
    daily = DailyOrchestrator(
        StubContextService([official_fact], [official_agenda])
    ).build()

    assert daily == {
        "facts": [official_fact],
        "priorities": [{
            "id": "official-fact",
            "title": "Official fact official-fact",
            "level": "Alta",
            "context": "Contexto geral",
        }],
        "analyses": [{
            "id": "official-fact",
            "title": "Official fact official-fact",
            "reason": "Official summary official-fact",
            "related_to": None,
            "status": "Contexto geral",
            "updated_at": "2026-07-28T10:00:00+00:00",
        }],
        "agenda": [official_agenda],
    }


def test_build_returns_all_four_blocks_as_lists():
    daily = DailyOrchestrator(StubContextService([])).build()

    assert set(daily) == {"facts", "priorities", "analyses", "agenda"}
    assert all(isinstance(block, list) for block in daily.values())


def test_build_returns_consistent_independent_structures():
    official_fact = fact("official-fact")
    official_agenda = agenda("official-agenda")
    orchestrator = DailyOrchestrator(
        StubContextService([official_fact], [official_agenda])
    )

    first = orchestrator.build()
    first["facts"].append("temporary fact")
    first["agenda"].append("temporary agenda")
    second = orchestrator.build()

    assert second == {
        "facts": [official_fact],
        "priorities": [{
            "id": "official-fact",
            "title": "Official fact official-fact",
            "level": "Alta",
            "context": "Contexto geral",
        }],
        "analyses": [{
            "id": "official-fact",
            "title": "Official fact official-fact",
            "reason": "Official summary official-fact",
            "related_to": None,
            "status": "Contexto geral",
            "updated_at": "2026-07-28T10:00:00+00:00",
        }],
        "agenda": [official_agenda],
    }
    assert first is not second
    assert all(first[name] is not second[name] for name in second)


def test_build_uses_the_official_facts_service():
    service = StubContextService([fact("official-fact")])

    daily = DailyOrchestrator(service).build()

    assert service.calls == [()]
    assert daily["facts"] == service.facts
    assert daily["facts"] is not service.facts


def test_build_uses_official_agenda_and_preserves_received_order():
    official_agenda = [agenda("portfolio-first"), agenda("general-second")]
    service = StubContextService([], official_agenda)

    daily = DailyOrchestrator(service).build()

    assert daily["agenda"] == official_agenda
    assert daily["agenda"] is not official_agenda


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

    daily = DailyOrchestrator(StubContextService(facts)).build()

    assert calls == [facts]
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

    daily = DailyOrchestrator(StubContextService(facts)).build()

    assert calls == [facts]
    assert daily["analyses"] is expected


def test_build_analyses_preserves_order_and_limits_to_two_items():
    facts = [fact("first"), fact("second"), fact("third")]

    analyses = DailyOrchestrator(StubContextService(facts)).build()["analyses"]

    assert [item["id"] for item in analyses] == ["first", "second"]
    assert all(set(item) == {
        "id", "title", "reason", "related_to", "status", "updated_at",
    } for item in analyses)


def test_build_preserves_priority_order_and_first_three_items():
    facts = [
        fact("first", "Alta", "Carteira"),
        fact("second", "Moderada", "Macro"),
        fact("third", "Baixa", "Mercado"),
        fact("fourth", "Baixa", "Mercado"),
    ]

    priorities = DailyOrchestrator(StubContextService(facts)).build()["priorities"]

    assert priorities == [
        {
            "id": "first",
            "title": "Official fact first",
            "level": "Alta",
            "context": "Carteira",
        },
        {
            "id": "second",
            "title": "Official fact second",
            "level": "Moderada",
            "context": "Macro",
        },
        {
            "id": "third",
            "title": "Official fact third",
            "level": "Baixa",
            "context": "Mercado",
        },
    ]
