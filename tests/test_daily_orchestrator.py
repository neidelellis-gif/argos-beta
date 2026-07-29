import backend.daily.orchestrator as orchestrator_module
from backend.daily.orchestrator import DailyOrchestrator


class StubContextService:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def generate(self, positions):
        self.calls.append(positions)
        return {"facts": self.facts}


def fact(identifier, priority="Alta", context="Contexto geral"):
    return {
        "id": identifier,
        "title": f"Official fact {identifier}",
        "priority": priority,
        "context": context,
    }


def test_build_creates_the_daily_structure():
    official_fact = fact("official-fact")
    daily = DailyOrchestrator(StubContextService([official_fact])).build()

    assert daily == {
        "facts": [official_fact],
        "priorities": [{
            "id": "official-fact",
            "title": "Official fact official-fact",
            "level": "Alta",
            "context": "Contexto geral",
        }],
        "analyses": [],
        "agenda": [],
    }


def test_build_returns_all_four_blocks_as_lists():
    daily = DailyOrchestrator(StubContextService([])).build()

    assert set(daily) == {"facts", "priorities", "analyses", "agenda"}
    assert all(isinstance(block, list) for block in daily.values())


def test_build_returns_consistent_independent_structures():
    official_fact = fact("official-fact")
    orchestrator = DailyOrchestrator(StubContextService([official_fact]))

    first = orchestrator.build()
    first["facts"].append("temporary fact")
    second = orchestrator.build()

    assert second == {
        "facts": [official_fact],
        "priorities": [{
            "id": "official-fact",
            "title": "Official fact official-fact",
            "level": "Alta",
            "context": "Contexto geral",
        }],
        "analyses": [],
        "agenda": [],
    }
    assert first is not second
    assert all(first[name] is not second[name] for name in second)


def test_build_uses_the_official_facts_service():
    service = StubContextService([fact("official-fact")])

    daily = DailyOrchestrator(service).build()

    assert service.calls == [()]
    assert daily["facts"] == service.facts
    assert daily["facts"] is not service.facts


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
