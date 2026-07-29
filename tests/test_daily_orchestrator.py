from backend.daily.orchestrator import DailyOrchestrator


def test_build_creates_the_daily_structure():
    daily = DailyOrchestrator().build()

    assert daily == {
        "facts": [],
        "priorities": [],
        "analyses": [],
        "agenda": [],
    }


def test_build_returns_all_four_blocks_as_lists():
    daily = DailyOrchestrator().build()

    assert set(daily) == {"facts", "priorities", "analyses", "agenda"}
    assert all(isinstance(block, list) for block in daily.values())


def test_build_returns_consistent_independent_structures():
    orchestrator = DailyOrchestrator()

    first = orchestrator.build()
    first["facts"].append("temporary fact")
    second = orchestrator.build()

    assert second == {
        "facts": [],
        "priorities": [],
        "analyses": [],
        "agenda": [],
    }
    assert first is not second
    assert all(first[name] is not second[name] for name in second)
