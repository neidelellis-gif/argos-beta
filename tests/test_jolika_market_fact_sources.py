from datetime import datetime, timezone

from backend.daily.models import ExternalDataResult, MarketEvent
from backend.important_facts import FactCandidate, FactCategory, FactImportance
from backend.jolika_market_fact_sources import load_market_context_facts


NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


class Provider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def fetch_facts(self, now, positions):
        if self.error:
            raise self.error
        return self.result


def official_fact():
    return FactCandidate(
        id="official-1", title="Fato oficial", description="Evidência oficial",
        source="Fonte oficial", published_at=NOW,
        importance=FactImportance.HIGH, urgency=FactImportance.HIGH,
        category=FactCategory.ECONOMY, related_currencies=("USD",),
    )


def test_professional_facts_are_appended_after_official_facts():
    event = MarketEvent(
        "news-1", "NVIDIA publica atualização", "Tecnologia", "Reuters",
        NOW, "Alta", "Atualização relacionada à NVIDIA.", ("NVDA",), False,
    )
    provider = Provider(ExternalDataResult("available", (event,)))
    result = load_market_context_facts((official_fact(),), (), provider, NOW)
    assert [item.id for item in result] == ["official-1", "professional-news-1"]
    assert result[1].source == "Reuters"
    assert result[1].related_assets == ("NVDA",)
    assert result[1].importance is FactImportance.HIGH
    assert result[1].category is FactCategory.MARKETS


def test_provider_failure_never_removes_official_facts():
    result = load_market_context_facts(
        (official_fact(),), (), Provider(error=RuntimeError("indisponível")), NOW
    )
    assert [item.id for item in result] == ["official-1"]


def test_unavailable_professional_source_keeps_official_facts_only():
    provider = Provider(ExternalDataResult("unavailable", (), error="sem conexão"))
    result = load_market_context_facts((official_fact(),), (), provider, NOW)
    assert [item.id for item in result] == ["official-1"]
