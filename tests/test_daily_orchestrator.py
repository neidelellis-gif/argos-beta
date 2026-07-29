from backend.daily.orchestrator import DailyOrchestrator


class StubContextService:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def generate(self, positions):
        self.calls.append(positions)
        return {"facts": self.facts}


def test_build_creates_the_daily_structure():
    fact = {"id": "official-fact", "title": "Official fact"}
    daily = DailyOrchestrator(StubContextService([fact])).build()

    assert daily == {
        "facts": [fact],
        "priorities": [],
        "analyses": [],
        "agenda": [],
    }


def test_build_returns_all_four_blocks_as_lists():
    daily = DailyOrchestrator(StubContextService([])).build()

    assert set(daily) == {"facts", "priorities", "analyses", "agenda"}
    assert all(isinstance(block, list) for block in daily.values())


def test_build_returns_consistent_independent_structures():
    fact = {"id": "official-fact"}
    orchestrator = DailyOrchestrator(StubContextService([fact]))

    first = orchestrator.build()
    first["facts"].append("temporary fact")
    second = orchestrator.build()

    assert second == {
        "facts": [fact],
        "priorities": [],
        "analyses": [],
        "agenda": [],
    }
    assert first is not second
    assert all(first[name] is not second[name] for name in second)


def test_build_uses_the_official_facts_service():
    service = StubContextService([{"id": "official-fact"}])

    daily = DailyOrchestrator(service).build()

    assert service.calls == [()]
    assert daily["facts"] == service.facts
    assert daily["facts"] is not service.facts
