from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.daily.cache import DailyCache
from backend.daily.context_service import AgendaEvent, DailyContextService, MarketEvent
from backend.daily.experience import (
    PANORAMA_TOPICS,
    build_priorities,
    build_daily_experience,
)
from backend.daily.providers import ExternalDataResult, FinnhubDailyProvider
from backend.daily.registry import (
    DailyProviderRegistry,
    build_default_registry,
    register_daily_provider,
)
from backend.models import PortfolioPosition

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)


def position(identifier, name=None, institution="UBS"):
    return PortfolioPosition(institution, None, None, None, name or identifier, identifier,
        "ticker", None, None, Decimal("100"), "USD", None, None, f"{institution}.csv")


def fact(identifier, hours, priority="Baixa", assets=(), category="Mercados", macro=False):
    return MarketEvent(identifier, f"Fato {identifier}", category, "Fonte real simulada",
        NOW - timedelta(hours=hours), priority, f"Resumo {identifier}", assets, macro)


def agenda(identifier, hours, assets=()):
    return AgendaEvent(identifier, f"Evento {identifier}", "Resultados",
        NOW + timedelta(hours=hours), "Fonte real simulada", "Moderada", assets)


class Provider:
    def __init__(self, facts=(), agenda=(), fail=False, name="test"):
        self.facts, self.agenda, self.fail, self.calls = facts, agenda, fail, 0
        self.name = name

    def _result(self, items):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provedor fora do ar")
        return ExternalDataResult("available" if items else "empty", tuple(items))

    def fetch_facts(self, now, positions): return self._result(self.facts)
    def fetch_agenda(self, now, positions): return self._result(self.agenda)


def service(tmp_path, provider):
    return DailyContextService(
        registry=DailyProviderRegistry((provider,)),
        cache=DailyCache(tmp_path, 60),
    )


def registry_service(tmp_path, *providers):
    return DailyContextService(
        registry=DailyProviderRegistry(providers),
        cache=DailyCache(tmp_path, 60),
    )


def test_window_limit_priority_order_and_expired_facts(tmp_path):
    facts = [fact("old", 25, "Alta"), fact("low", 1), fact("high-old", 8, "Alta"),
             fact("high-new", 2, "Alta"), fact("moderate", 1, "Moderada"),
             fact("extra-1", 3), fact("extra-2", 4)]
    result = service(tmp_path, Provider(facts)).generate((), now=NOW)
    assert len(result["facts"]) == 5
    assert [item["id"] for item in result["facts"][:3]] == ["high-new", "high-old", "moderate"]
    assert "old" not in {item["id"] for item in result["facts"]}


def test_experience_uses_the_official_priorities_transformation(tmp_path):
    daily = build_daily_experience(
        (),
        date(2026, 7, 28),
        NOW,
        service(tmp_path, Provider([
            fact("first", 1, "Alta"),
            fact("second", 2, "Moderada"),
            fact("third", 3, "Baixa"),
            fact("fourth", 4, "Baixa"),
        ])),
    )

    assert daily["priorities"] == build_priorities(daily["important_facts"])


def test_direct_nvda_and_ethereum_relationships_without_indirect_etf_match(tmp_path):
    positions = [position("NVDA", "NVIDIA Corp"), position("ETHB", "Ethereum Brasil", "Santander"),
                 position("TECH", "Technology ETF")]
    result = service(tmp_path, Provider([
        fact("nvidia", 2, "Moderada", ("NVDA", "NVIDIA"), "Tecnologia"),
        fact("eth", 3, "Moderada", ("ETH", "ETHEREUM"), "Criptoativos"),
    ])).generate(positions, NOW)
    assert result["facts"][0]["matched_portfolio_assets"] == ["NVDA"]
    assert result["facts"][1]["matched_portfolio_assets"] == ["ETHB"]
    assert all("TECH" not in item["matched_portfolio_assets"] for item in result["facts"])


def test_works_without_portfolio_and_with_ubs_and_santander(tmp_path):
    provider = Provider([fact("macro", 1, "Alta", macro=True)])
    no_portfolio = service(tmp_path / "a", provider).generate((), NOW)
    combined = service(tmp_path / "b", Provider(provider.facts)).generate(
        [position("AAA", institution="UBS"), position("BBB", institution="Santander")], NOW)
    assert no_portfolio["facts"][0]["context"] == "Contexto macro geral de mercado"
    assert combined["facts"][0]["context"] == "Impacto macro para as carteiras"


def test_agenda_prioritizes_portfolio_then_chronology_and_excludes_past(tmp_path):
    events = [agenda("general-first", 1), agenda("portfolio-later", 4, ("NVDA",)),
              agenda("portfolio-first", 2, ("NVDA",)), agenda("past", -1)]
    result = service(tmp_path, Provider(agenda=events)).generate([position("NVDA")], NOW)
    assert [item["id"] for item in result["agenda"]] == [
        "portfolio-first", "portfolio-later", "general-first"]


def test_legitimate_empty_and_provider_failure_are_distinct(tmp_path):
    empty = service(tmp_path / "empty", Provider()).generate((), NOW)
    failed = service(tmp_path / "failed", Provider(fail=True)).generate((), NOW)
    assert empty["sources"]["facts"]["status"] == "empty"
    assert failed["sources"]["facts"]["status"] == "unavailable"
    assert "fora do ar" in failed["sources"]["facts"]["error"]


def test_missing_credential_is_controlled(tmp_path):
    provider = FinnhubDailyProvider(api_key="")
    result = service(tmp_path, provider).generate((), NOW)
    assert result["sources"]["facts"]["status"] == "unavailable"
    assert "FINNHUB_API_KEY" in result["sources"]["facts"]["error"]


def test_cache_avoids_calls_and_preserves_last_valid_on_failure(tmp_path):
    cache = DailyCache(tmp_path, 60)
    good = Provider([fact("valid", 1)], [agenda("future", 1)])
    registry = DailyProviderRegistry((good,))
    first = DailyContextService(registry=registry, cache=cache).generate((), NOW)
    second = DailyContextService(registry=registry, cache=cache).generate(
        (), NOW + timedelta(seconds=30)
    )
    assert good.calls == 2
    assert second["sources"]["facts"]["cached"] is True
    failing = Provider(fail=True)
    stale = DailyContextService(
        registry=DailyProviderRegistry((failing,)),
        cache=DailyCache(tmp_path, 1),
    ).generate((), NOW + timedelta(seconds=2))
    assert stale["facts"][0]["id"] == first["facts"][0]["id"]
    assert stale["sources"]["facts"]["cached"] is True
    assert stale["sources"]["facts"]["status"] == "unavailable"


def test_registry_queries_two_active_providers_in_priority_order(tmp_path):
    first = Provider([fact("first", 1)], name="first")
    second = Provider([fact("second", 2)], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert {item["id"] for item in result["facts"]} == {"first", "second"}
    assert first.calls == 2
    assert second.calls == 2
    assert [provider.name for provider in DailyProviderRegistry(
        (first, second)
    ).providers] == ["first", "second"]


def test_registered_provider_order_is_configurable():
    register_daily_provider("future-a", lambda: Provider(name="future-a"))
    register_daily_provider("future-b", lambda: Provider(name="future-b"))

    registry = build_default_registry("future-b,future-a")

    assert [provider.name for provider in registry.providers] == [
        "future-b", "future-a",
    ]


def test_registry_falls_back_when_first_provider_fails(tmp_path):
    first = Provider(fail=True, name="first")
    second = Provider([fact("fallback", 1)], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert [item["id"] for item in result["facts"]] == ["fallback"]
    assert result["sources"]["facts"]["status"] == "available"


def test_registry_combines_results_when_both_providers_respond(tmp_path):
    first = Provider([fact("alpha", 1)], [agenda("calendar-a", 2)], name="first")
    second = Provider([fact("beta", 2)], [agenda("calendar-b", 3)], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert {item["id"] for item in result["facts"]} == {"alpha", "beta"}
    assert {item["id"] for item in result["agenda"]} == {
        "calendar-a", "calendar-b",
    }


def test_registry_deduplicates_same_normalized_event(tmp_path):
    preferred = fact("preferred-id", 1, assets=("NVDA",), category="Tecnologia")
    duplicate = MarketEvent(
        "duplicate-id",
        "  FATO PREFERRED-ID  ",
        "tecnologia",
        "second source",
        preferred.occurred_at,
        preferred.priority,
        "Outro resumo",
        ("nvda",),
    )
    first = Provider([preferred], name="first")
    second = Provider([duplicate], name="second")

    result = registry_service(tmp_path, first, second).generate((), NOW)

    assert [item["id"] for item in result["facts"]] == ["preferred-id"]
    assert result["facts"][0]["source"] == "Fonte real simulada"


def test_registry_reports_unavailable_when_both_providers_fail(tmp_path):
    result = registry_service(
        tmp_path,
        Provider(fail=True, name="first"),
        Provider(fail=True, name="second"),
    ).generate((), NOW)

    assert result["facts"] == []
    assert result["sources"]["facts"]["status"] == "unavailable"
    assert "first" in result["sources"]["facts"]["error"]
    assert "second" in result["sources"]["facts"]["error"]


def test_registry_treats_two_empty_responses_as_legitimate_empty(tmp_path):
    result = registry_service(
        tmp_path,
        Provider(name="first"),
        Provider(name="second"),
    ).generate((), NOW)

    assert result["sources"]["facts"]["status"] == "empty"


def test_provider_normalizes_news_and_calendars():
    news = FinnhubDailyProvider.normalize_news([{
        "id": 1, "headline": "NVIDIA announces platform", "summary": "NVDA update",
        "datetime": int(NOW.timestamp()), "source": "Reuters", "related": "NVDA"}])
    calendar = FinnhubDailyProvider.normalize_calendar(
        {"economicCalendar": [{"date": "2026-07-29T12:00:00Z", "event": "CPI inflation", "impact": 3}]},
        {"earningsCalendar": [{"date": "2026-07-30", "symbol": "NVDA"}]})
    assert news[0].category == "Tecnologia" and news[0].related_assets == ("NVDA", "NVIDIA")
    assert calendar[0].category == "Inflação" and calendar[0].importance == "Alta"
    assert calendar[1].related_assets == ("NVDA",)
    assert calendar[1].time_explicit is False


def test_provider_normalizes_available_dividends():
    calendar = FinnhubDailyProvider.normalize_calendar({}, {}, [{
        "date": "2026-07-31", "symbol": "NVDA", "amount": 0.01,
    }])
    assert calendar[0].category == "Dividendos"
    assert calendar[0].related_assets == ("NVDA",)
    assert calendar[0].time_explicit is False


def test_experience_neutral_panorama_and_empty_agenda(tmp_path):
    daily = build_daily_experience((), date(2026, 7, 28), NOW,
        service(tmp_path, Provider([fact("market", 1)])))
    assert tuple(item["topic"] for item in daily["global_overview"]) == PANORAMA_TOPICS
    assert daily["market_agenda"] == []
    assert daily["global_overview"][0]["summary"] == "Nenhum fato relevante identificado nas últimas 24 horas."
    assert "etapa futura" not in str(daily)


def test_no_legacy_production_mocks_remain():
    from pathlib import Path
    production = "\n".join(path.read_text(encoding="utf-8") for path in Path("backend").rglob("*.py"))
    for legacy in ("Mock Federal Reserve", "nvidia-chips", "ethereum-network", "global-equities", "oil-supply"):
        assert legacy not in production
